from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import (
    CheckConstraint,
    Index,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    SmallInteger,
    String,
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.enums import Category, Period, Status

Money = Numeric(12, 2)


def _pg_enum(enum_cls: type[Enum], name: str) -> SAEnum:
    return SAEnum(enum_cls, name=name, values_callable=lambda e: [m.value for m in e])


class Base(DeclarativeBase):
    pass


class Subscription(Base):
    __tablename__ = "subscriptions"
    __table_args__ = (
        CheckConstraint("price > 0", name="price_positive"),
        CheckConstraint("billing_day BETWEEN 1 AND 31", name="billing_day_range"),
        Index("idx_category", "category"),
        Index("idx_status", "status"),
        Index("idx_next_payment", "next_payment_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    price: Mapped[Decimal] = mapped_column(Money)
    period: Mapped[Period] = mapped_column(_pg_enum(Period, "billing_period"))
    next_payment_date: Mapped[date] = mapped_column(Date)
    # День месяца, в который списываются деньги. Благодаря ему после февраля
    # дата возвращается с 28 числа на 31
    billing_day: Mapped[int] = mapped_column(SmallInteger)
    category: Mapped[Category] = mapped_column(
        _pg_enum(Category, "subscription_category"), server_default=Category.OTHER.value
    )
    status: Mapped[Status] = mapped_column(
        _pg_enum(Status, "subscription_status"), server_default=Status.ACTIVE.value
    )
    trial_end_date: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    payments: Mapped[list["Payment"]] = relationship(
        back_populates="subscription", cascade="all, delete-orphan", passive_deletes=True
    )


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("amount > 0", name="amount_positive"),
        Index("idx_subscription", "subscription_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    subscription_id: Mapped[int] = mapped_column(ForeignKey("subscriptions.id", ondelete="CASCADE"))
    amount: Mapped[Decimal] = mapped_column(Money)
    # Дата списания, за которую внесли этот платёж
    billing_date: Mapped[date] = mapped_column(Date)
    paid_at: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    subscription: Mapped[Subscription] = relationship(back_populates="payments")
