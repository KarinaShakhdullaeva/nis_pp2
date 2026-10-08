from calendar import monthrange
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Protocol

from app.enums import Category, EventType, Period, Status

CENT = Decimal("0.01")
WEEKS_PER_YEAR = 52
MONTHS_PER_YEAR = 12
_PERIOD_MONTHS = {Period.MONTH: 1, Period.YEAR: 12}


class SubscriptionLike(Protocol):
    id: int
    name: str
    price: Decimal
    period: Period
    next_payment_date: date
    billing_day: int
    category: Category
    status: Status
    trial_end_date: date | None


def to_money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def monthly_price(price: Decimal, period: Period) -> Decimal:
    if period == Period.WEEK:
        exact = price * WEEKS_PER_YEAR / MONTHS_PER_YEAR
    elif period == Period.YEAR:
        exact = price / MONTHS_PER_YEAR
    else:
        exact = price
    return to_money(exact)


def add_months(start: date, months: int, billing_day: int | None = None) -> date:
    day = billing_day or start.day
    month_index = start.month - 1 + months
    year, month = start.year + month_index // 12, month_index % 12 + 1
    return date(year, month, min(day, monthrange(year, month)[1]))


def nth_date(start: date, period: Period, n: int, billing_day: int | None = None) -> date:
    if n == 0:
        return start
    if period == Period.WEEK:
        return start + timedelta(weeks=n)
    return add_months(start, n * _PERIOD_MONTHS[period], billing_day)


def next_date(current: date, period: Period, billing_day: int | None = None) -> date:
    return nth_date(current, period, 1, billing_day)


# Номер считается по разнице дат, чтобы не перебирать все прошлые списания
def _first_index_from(
    start: date, period: Period, target: date, billing_day: int | None
) -> int:
    if start >= target:
        return 0
    if period == Period.WEEK:
        return -(-(target - start).days // 7)  # деление с округлением вверх
    months_between = (target.year - start.year) * 12 + target.month - start.month
    n = max(months_between // _PERIOD_MONTHS[period] - 1, 0)
    while nth_date(start, period, n, billing_day) < target:
        n += 1
    return n


def dates_between(
    start: date, period: Period, date_from: date, date_to: date, billing_day: int | None = None
) -> Iterator[date]:
    n = _first_index_from(start, period, date_from, billing_day)
    while (current := nth_date(start, period, n, billing_day)) <= date_to:
        yield current
        n += 1


@dataclass(frozen=True)
class CategoryTotal:
    category: Category
    total: Decimal
    count: int


@dataclass(frozen=True)
class MonthlySummary:
    total: Decimal
    active_subscriptions: int
    by_category: list[CategoryTotal]


# Каждая подписка округляется до копеек до сложения,
# поэтому общий итог всегда совпадает с суммой по категориям
def build_summary(subscriptions: Iterable[SubscriptionLike]) -> MonthlySummary:
    totals: dict[Category, Decimal] = defaultdict(Decimal)
    counts: Counter[Category] = Counter()
    for sub in subscriptions:
        if sub.status != Status.ACTIVE:
            continue
        totals[sub.category] += monthly_price(sub.price, sub.period)
        counts[sub.category] += 1

    by_category = sorted(
        (CategoryTotal(category, to_money(total), counts[category]) for category, total in totals.items()),
        key=lambda item: (-item.total, item.category.value),
    )
    return MonthlySummary(
        total=to_money(sum(totals.values(), Decimal(0))),
        active_subscriptions=sum(counts.values()),
        by_category=by_category,
    )


@dataclass(frozen=True)
class UpcomingEvent:
    subscription_id: int
    name: str
    category: Category
    type: EventType
    due_date: date
    amount: Decimal
    overdue: bool = False


# Окно начинается сегодня и длится days дней
def upcoming_window(today: date, days: int) -> tuple[date, date]:
    return today, today + timedelta(days=days - 1)


def build_upcoming(
    subscriptions: Iterable[SubscriptionLike], today: date, days: int
) -> list[UpcomingEvent]:
    date_from, date_to = upcoming_window(today, days)
    events: list[UpcomingEvent] = []

    for sub in subscriptions:
        if sub.status != Status.ACTIVE:
            continue
        common = {
            "subscription_id": sub.id,
            "name": sub.name,
            "category": sub.category,
            "amount": sub.price,
        }
        if sub.next_payment_date < date_from:
            events.append(
                UpcomingEvent(**common, type=EventType.PAYMENT, due_date=sub.next_payment_date, overdue=True)
            )
        for due in dates_between(sub.next_payment_date, sub.period, date_from, date_to, sub.billing_day):
            events.append(UpcomingEvent(**common, type=EventType.PAYMENT, due_date=due))
        if sub.trial_end_date is not None and date_from <= sub.trial_end_date <= date_to:
            events.append(UpcomingEvent(**common, type=EventType.TRIAL_END, due_date=sub.trial_end_date))

    # Сортировка по дате, в один день конец пробного периода идёт раньше списания
    events.sort(key=lambda e: (e.due_date, e.type != EventType.TRIAL_END, e.name.lower(), e.subscription_id))
    return events


def upcoming_total(events: Iterable[UpcomingEvent]) -> Decimal:
    return to_money(sum((e.amount for e in events if e.type == EventType.PAYMENT), Decimal(0)))
