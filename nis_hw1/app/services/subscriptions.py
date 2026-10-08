from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from sqlalchemy import case, select
from sqlalchemy.orm import Session

from app.enums import Category, Period, SortField, SortOrder, Status
from app.errors import ConflictError, NotFoundError, ValidationApiError
from app.models import Payment, Subscription
from app.schemas import PaymentCreate, SubscriptionCreate, SubscriptionUpdate
from app.services.billing import next_date

_MONTHLY_PRICE = case(
    (Subscription.period == Period.WEEK, Subscription.price * 52 / 12),
    (Subscription.period == Period.YEAR, Subscription.price / 12),
    else_=Subscription.price,
)

_SORT_COLUMNS = {
    SortField.PRICE: Subscription.price,
    SortField.MONTHLY_PRICE: _MONTHLY_PRICE,
    SortField.NEXT_PAYMENT_DATE: Subscription.next_payment_date,
    SortField.NAME: Subscription.name,
    SortField.CREATED_AT: Subscription.created_at,
}

_STATUS_LABELS = {Status.PAUSED: "приостановлена", Status.CANCELLED: "отменена"}


def get_subscription(db: Session, subscription_id: int, *, for_update: bool = False) -> Subscription:
    subscription = db.get(Subscription, subscription_id, with_for_update=for_update)
    if subscription is None:
        raise NotFoundError(f"Подписка с id={subscription_id} не найдена")
    return subscription


def list_subscriptions(
    db: Session,
    *,
    category: Category | None,
    status: Status | None,
    sort_by: SortField,
    order: SortOrder,
) -> Sequence[Subscription]:
    stmt = select(Subscription)
    if category is not None:
        stmt = stmt.where(Subscription.category == category)
    if status is not None:
        stmt = stmt.where(Subscription.status == status)
    column = _SORT_COLUMNS[sort_by]
    stmt = stmt.order_by(column.desc() if order == SortOrder.DESC else column.asc(), Subscription.id)
    return db.scalars(stmt).all()


def list_active(db: Session) -> Sequence[Subscription]:
    return db.scalars(select(Subscription).where(Subscription.status == Status.ACTIVE)).all()


def create_subscription(db: Session, data: SubscriptionCreate) -> Subscription:
    subscription = Subscription(
        **data.model_dump(),
        status=Status.ACTIVE,
        billing_day=data.next_payment_date.day,
    )
    db.add(subscription)
    db.commit()
    db.refresh(subscription)
    return subscription


def update_subscription(db: Session, subscription_id: int, data: SubscriptionUpdate) -> Subscription:
    subscription = get_subscription(db, subscription_id)
    changes = data.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(subscription, field, value)
    if "next_payment_date" in changes:
        # Новая дата задаёт и новый день списания
        subscription.billing_day = subscription.next_payment_date.day
    db.commit()
    db.refresh(subscription)
    return subscription


def delete_subscription(db: Session, subscription_id: int) -> None:
    subscription = get_subscription(db, subscription_id)
    db.delete(subscription)
    db.commit()


def change_status(db: Session, subscription_id: int, status: Status) -> Subscription:
    subscription = get_subscription(db, subscription_id)
    subscription.status = status
    db.commit()
    db.refresh(subscription)
    return subscription


def add_payment(
    db: Session, subscription_id: int, data: PaymentCreate, today: date
) -> tuple[Payment, Subscription]:
    # Строка блокируется, чтобы два одновременных запроса не сдвинули дату дважды
    subscription = get_subscription(db, subscription_id, for_update=True)
    if subscription.status != Status.ACTIVE:
        raise ConflictError(
            f"Нельзя отметить оплату, потому что подписка {_STATUS_LABELS[subscription.status]}. "
            "Сначала сделайте её активной."
        )
    paid_at = data.paid_at or today
    if paid_at > today:
        raise ValidationApiError("paid_at", "Дата оплаты не может быть в будущем")

    payment = Payment(
        subscription_id=subscription.id,
        amount=data.amount if data.amount is not None else subscription.price,
        billing_date=subscription.next_payment_date,
        paid_at=paid_at,
    )
    subscription.next_payment_date = next_date(
        subscription.next_payment_date, subscription.period, subscription.billing_day
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)
    db.refresh(subscription)
    return payment, subscription


def list_payments(db: Session, subscription_id: int) -> tuple[Sequence[Payment], Decimal]:
    get_subscription(db, subscription_id)
    payments = db.scalars(
        select(Payment)
        .where(Payment.subscription_id == subscription_id)
        .order_by(Payment.paid_at.desc(), Payment.id.desc())
    ).all()
    total = sum((p.amount for p in payments), Decimal("0.00"))
    return payments, total
