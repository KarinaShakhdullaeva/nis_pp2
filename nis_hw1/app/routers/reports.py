from typing import Annotated

from fastapi import APIRouter, Query

from app.config import get_settings
from app.deps import DbSession, Today
from app.errors import ErrorResponse
from app.schemas import CategoryTotalRead, MonthlySummaryRead, UpcomingItem, UpcomingRead
from app.services import billing
from app.services.subscriptions import list_active

router = APIRouter(
    tags=["Аналитика"],
    responses={422: {"model": ErrorResponse, "description": "Ошибка валидации входных данных"}},
)


@router.get(
    "/stats/monthly",
    response_model=MonthlySummaryRead,
    summary="Расходы в месяц",
    description=(
        "Показывает, сколько в месяц уходит на активные подписки, и делит сумму по категориям. "
        "Недельная цена умножается на 52 и делится на 12, а годовая делится на 12."
    ),
)
def monthly_summary(db: DbSession):
    summary = billing.build_summary(list_active(db))
    return MonthlySummaryRead(
        currency=get_settings().currency,
        total=summary.total,
        active_subscriptions=summary.active_subscriptions,
        by_category=[CategoryTotalRead.model_validate(c) for c in summary.by_category],
    )


@router.get(
    "/payments/upcoming",
    response_model=UpcomingRead,
    summary="Ближайшие платежи",
    description=(
        "Показывает списания по активным подпискам на ближайшие `days` дней, считая сегодняшний. "
        "Также показывает окончания пробных периодов и просроченные списания."
    ),
)
def upcoming_payments(
    db: DbSession,
    today: Today,
    days: Annotated[int, Query(ge=1, le=365, description="Сколько дней показывать, начиная с сегодняшнего")] = 7,
):
    events = billing.build_upcoming(list_active(db), today, days)
    date_from, date_to = billing.upcoming_window(today, days)
    return UpcomingRead(
        currency=get_settings().currency,
        days=days,
        date_from=date_from,
        date_to=date_to,
        total=billing.upcoming_total(events),
        items=[
            UpcomingItem(
                subscription_id=e.subscription_id,
                name=e.name,
                category=e.category,
                type=e.type,
                due_date=e.due_date,
                days_left=(e.due_date - today).days,
                amount=e.amount,
                overdue=e.overdue,
            )
            for e in events
        ],
    )
