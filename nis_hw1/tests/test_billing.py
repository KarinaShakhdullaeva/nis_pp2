from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import pytest

from app.enums import Category, EventType, Period, Status
from app.services.billing import (
    add_months,
    dates_between,
    build_summary,
    build_upcoming,
    monthly_price,
    next_date,
    upcoming_total,
)

D = Decimal


@dataclass
class Sub:
    id: int = 1
    name: str = "Сервис"
    price: Decimal = D("100.00")
    period: Period = Period.MONTH
    next_payment_date: date = date(2026, 1, 20)
    billing_day: int | None = None
    category: Category = Category.OTHER
    status: Status = Status.ACTIVE
    trial_end_date: date | None = None

    def __post_init__(self) -> None:
        if self.billing_day is None:
            self.billing_day = self.next_payment_date.day


@pytest.mark.parametrize(
    ("price", "period", "expected"),
    [
        (D("299.00"), Period.MONTH, D("299.00")),
        (D("1200.00"), Period.YEAR, D("100.00")),
        (D("1000.00"), Period.YEAR, D("83.33")),
        (D("2000.00"), Period.YEAR, D("166.67")),
        (D("100.00"), Period.WEEK, D("433.33")),  # 100 * 52 / 12
        (D("99.99"), Period.WEEK, D("433.29")),
        (D("0.06"), Period.YEAR, D("0.01")),  # 0.005 округляется вверх
    ],
)
def test_monthly_price(price, period, expected):
    assert monthly_price(price, period) == expected


def test_week_is_not_four_weeks():
    assert monthly_price(D("100"), Period.WEEK) != D("400.00")


def test_monthly_price_is_decimal():
    result = monthly_price(D("0.10"), Period.WEEK)
    assert isinstance(result, Decimal)
    assert result == D("0.43")


@pytest.mark.parametrize(
    ("start", "months", "expected"),
    [
        (date(2026, 1, 15), 1, date(2026, 2, 15)),
        (date(2026, 1, 31), 1, date(2026, 2, 28)),
        (date(2028, 1, 31), 1, date(2028, 2, 29)),
        (date(2026, 12, 10), 1, date(2027, 1, 10)),
        (date(2026, 3, 31), 1, date(2026, 4, 30)),
        (date(2026, 5, 5), 12, date(2027, 5, 5)),
        (date(2026, 11, 30), 3, date(2027, 2, 28)),
    ],
)
def test_add_months(start, months, expected):
    assert add_months(start, months) == expected


def test_next_week():
    assert next_date(date(2026, 12, 29), Period.WEEK) == date(2027, 1, 5)


def test_month_keeps_day():
    d = date(2026, 1, 31)
    chain = []
    for _ in range(4):
        d = next_date(d, Period.MONTH, billing_day=31)
        chain.append(d)
    assert chain == [date(2026, 2, 28), date(2026, 3, 31), date(2026, 4, 30), date(2026, 5, 31)]


def test_leap_year():
    assert next_date(date(2028, 2, 29), Period.YEAR, billing_day=29) == date(2029, 2, 28)
    assert next_date(date(2031, 2, 28), Period.YEAR, billing_day=29) == date(2032, 2, 29)


def test_weekly_dates():
    dates = list(dates_between(date(2026, 1, 1), Period.WEEK, date(2026, 1, 1), date(2026, 1, 30)))
    assert dates == [date(2026, 1, d) for d in (1, 8, 15, 22, 29)]


def test_old_monthly_start():
    dates = list(
        dates_between(date(2020, 1, 31), Period.MONTH, date(2026, 2, 1), date(2026, 3, 31), billing_day=31)
    )
    assert dates == [date(2026, 2, 28), date(2026, 3, 31)]


def test_yearly_outside_window():
    assert list(dates_between(date(2026, 6, 1), Period.YEAR, date(2026, 1, 1), date(2026, 5, 31))) == []


def test_old_weekly_start():
    dates = list(dates_between(date(2001, 1, 1), Period.WEEK, date(2026, 1, 15), date(2026, 1, 21)))
    assert len(dates) == 1
    assert date(2026, 1, 15) <= dates[0] <= date(2026, 1, 21)


def test_summary_by_category():
    subs = [
        Sub(id=1, price=D("799.00"), period=Period.MONTH, category=Category.ENTERTAINMENT),
        Sub(id=2, price=D("2400.00"), period=Period.YEAR, category=Category.ENTERTAINMENT),
        Sub(id=3, price=D("100.00"), period=Period.WEEK, category=Category.WORK),
        Sub(id=4, price=D("5000.00"), period=Period.MONTH, category=Category.WORK, status=Status.PAUSED),
        Sub(id=5, price=D("300.00"), period=Period.MONTH, category=Category.MUSIC, status=Status.CANCELLED),
    ]
    summary = build_summary(subs)

    assert summary.total == D("1432.33")  # 799 + 200 + 433.33
    assert summary.active_subscriptions == 3
    assert [(c.category, c.total, c.count) for c in summary.by_category] == [
        (Category.ENTERTAINMENT, D("999.00"), 2),
        (Category.WORK, D("433.33"), 1),
    ]


def test_summary_total():
    subs = [Sub(id=i, price=D("1000.00"), period=Period.YEAR, category=c) for i, c in enumerate(Category)]
    summary = build_summary(subs)
    assert summary.total == sum(c.total for c in summary.by_category)
    assert summary.total == D("83.33") * len(Category)


def test_summary_empty():
    summary = build_summary([])
    assert summary.total == D("0.00")
    assert str(summary.total) == "0.00"
    assert summary.by_category == []


TODAY = date(2026, 1, 15)


def test_window_edges():
    subs = [
        Sub(id=1, name="today", next_payment_date=TODAY),
        Sub(id=2, name="last day", next_payment_date=date(2026, 1, 21)),  # today + 6
        Sub(id=3, name="outside", next_payment_date=date(2026, 1, 22)),  # today + 7
    ]
    events = build_upcoming(subs, TODAY, days=7)
    assert [e.name for e in events] == ["today", "last day"]


def test_weekly_several_times():
    sub = Sub(price=D("150.00"), period=Period.WEEK, next_payment_date=date(2026, 1, 16))
    events = build_upcoming([sub], TODAY, days=30)
    assert [e.due_date for e in events] == [
        date(2026, 1, 16), date(2026, 1, 23), date(2026, 1, 30), date(2026, 2, 6), date(2026, 2, 13)
    ]
    assert upcoming_total(events) == D("750.00")


def test_inactive_skipped():
    subs = [
        Sub(id=1, status=Status.PAUSED, next_payment_date=TODAY),
        Sub(id=2, status=Status.CANCELLED, next_payment_date=TODAY),
    ]
    assert build_upcoming(subs, TODAY, days=7) == []


def test_trial_end():
    sub = Sub(price=D("299.00"), next_payment_date=date(2026, 1, 18), trial_end_date=date(2026, 1, 17))
    events = build_upcoming([sub], TODAY, days=7)
    assert [(e.type, e.due_date) for e in events] == [
        (EventType.TRIAL_END, date(2026, 1, 17)),
        (EventType.PAYMENT, date(2026, 1, 18)),
    ]
    assert upcoming_total(events) == D("299.00")


def test_trial_end_first():
    sub = Sub(next_payment_date=TODAY, trial_end_date=TODAY)
    events = build_upcoming([sub], TODAY, days=1)
    assert [e.type for e in events] == [EventType.TRIAL_END, EventType.PAYMENT]


def test_overdue():
    sub = Sub(next_payment_date=date(2026, 1, 10))
    events = build_upcoming([sub], TODAY, days=30)
    assert [(e.due_date, e.overdue) for e in events] == [(date(2026, 1, 10), True), (date(2026, 2, 10), False)]
    assert upcoming_total(events) == D("200.00")


def test_sorted_by_date():
    subs = [
        Sub(id=1, name="B", next_payment_date=date(2026, 1, 19)),
        Sub(id=2, name="A", next_payment_date=date(2026, 1, 16)),
        Sub(id=3, name="C", next_payment_date=date(2026, 1, 16)),
    ]
    assert [e.name for e in build_upcoming(subs, TODAY, days=7)] == ["A", "C", "B"]
