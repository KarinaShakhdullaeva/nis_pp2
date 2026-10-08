from typing import Annotated

from fastapi import APIRouter, Body, Response

from app.deps import DbSession, Today
from app.enums import Category, SortField, SortOrder, Status
from app.errors import ErrorResponse
from app.schemas import (
    PaymentCreate,
    PaymentHistory,
    PaymentRead,
    PaymentResult,
    StatusUpdate,
    SubscriptionCreate,
    SubscriptionRead,
    SubscriptionUpdate,
)
from app.services import subscriptions as service

router = APIRouter(
    prefix="/subscriptions",
    tags=["Подписки"],
    responses={422: {"model": ErrorResponse, "description": "Ошибка валидации входных данных"}},
)

NOT_FOUND = {404: {"model": ErrorResponse, "description": "Подписка не найдена"}}


@router.post(
    "",
    status_code=201,
    response_model=SubscriptionRead,
    summary="Создать подписку",
    description="Создаёт подписку со статусом `active`.",
)
def create_subscription(payload: SubscriptionCreate, db: DbSession, response: Response):
    subscription = service.create_subscription(db, payload)
    response.headers["Location"] = f"/subscriptions/{subscription.id}"
    return subscription


@router.get(
    "",
    response_model=list[SubscriptionRead],
    summary="Список подписок",
    description="Список можно отфильтровать по категории и статусу и отсортировать по полю `sort_by`.",
)
def list_subscriptions(
    db: DbSession,
    category: Category | None = None,
    status: Status | None = None,
    sort_by: SortField = SortField.NEXT_PAYMENT_DATE,
    order: SortOrder = SortOrder.ASC,
):
    return service.list_subscriptions(db, category=category, status=status, sort_by=sort_by, order=order)


@router.get(
    "/{subscription_id}",
    response_model=SubscriptionRead,
    responses=NOT_FOUND,
    summary="Подписка по id",
    description="Показывает одну подписку по её id.",
)
def get_subscription(subscription_id: int, db: DbSession):
    return service.get_subscription(db, subscription_id)


@router.patch(
    "/{subscription_id}",
    response_model=SubscriptionRead,
    responses=NOT_FOUND,
    summary="Изменить подписку",
    description=(
        "Передайте только те поля, которые нужно изменить. "
        "Если поменять `next_payment_date`, списания дальше будут идти в день этой даты."
    ),
)
def update_subscription(subscription_id: int, payload: SubscriptionUpdate, db: DbSession):
    return service.update_subscription(db, subscription_id, payload)


@router.delete(
    "/{subscription_id}",
    status_code=204,
    responses=NOT_FOUND,
    summary="Удалить подписку",
    description="Удаляет подписку вместе с историей платежей.",
)
def delete_subscription(subscription_id: int, db: DbSession) -> Response:
    service.delete_subscription(db, subscription_id)
    return Response(status_code=204)


@router.patch(
    "/{subscription_id}/status",
    response_model=SubscriptionRead,
    responses=NOT_FOUND,
    summary="Сменить статус",
    description=(
        "Подписку можно сделать активной, поставить на паузу или отменить. "
        "Неактивные подписки не входят в расходы и ближайшие платежи, и их нельзя оплатить."
    ),
)
def change_status(subscription_id: int, payload: StatusUpdate, db: DbSession):
    return service.change_status(db, subscription_id, payload.status)


@router.post(
    "/{subscription_id}/payments",
    status_code=201,
    response_model=PaymentResult,
    responses={
        **NOT_FOUND,
        409: {"model": ErrorResponse, "description": "Подписка не активна"},
    },
    summary="Отметить оплату",
    description=(
        "Записывает платёж в историю и сдвигает `next_payment_date` на один период. "
        "Тело запроса можно не передавать."
    ),
)
def add_payment(
    subscription_id: int,
    db: DbSession,
    today: Today,
    payload: Annotated[PaymentCreate | None, Body()] = None,
):
    payment, subscription = service.add_payment(db, subscription_id, payload or PaymentCreate(), today)
    return PaymentResult(
        payment=PaymentRead.model_validate(payment),
        subscription=SubscriptionRead.model_validate(subscription),
    )


@router.get(
    "/{subscription_id}/payments",
    response_model=PaymentHistory,
    responses=NOT_FOUND,
    summary="История платежей",
    description="Показывает платежи от новых к старым, их количество и общую сумму.",
)
def list_payments(subscription_id: int, db: DbSession):
    payments, total = service.list_payments(db, subscription_id)
    return PaymentHistory(
        subscription_id=subscription_id,
        count=len(payments),
        total_paid=total,
        items=[PaymentRead.model_validate(p) for p in payments],
    )
