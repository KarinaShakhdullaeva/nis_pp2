"""Таблицы подписок и платежей

Revision ID: 0001
Revises:
Create Date: 2026-10-01
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

billing_period = sa.Enum("week", "month", "year", name="billing_period")
subscription_category = sa.Enum(
    "entertainment", "music", "education", "work", "software", "health", "other",
    name="subscription_category",
)
subscription_status = sa.Enum("active", "paused", "cancelled", name="subscription_status")


def upgrade() -> None:
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("price", sa.Numeric(12, 2), nullable=False),
        sa.Column("period", billing_period, nullable=False),
        sa.Column("next_payment_date", sa.Date(), nullable=False),
        sa.Column("billing_day", sa.SmallInteger(), nullable=False),
        sa.Column("category", subscription_category, server_default="other", nullable=False),
        sa.Column("status", subscription_status, server_default="active", nullable=False),
        sa.Column("trial_end_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("price > 0", name="price_positive"),
        sa.CheckConstraint("billing_day BETWEEN 1 AND 31", name="billing_day_range"),
    )
    op.create_index("idx_category", "subscriptions", ["category"])
    op.create_index("idx_status", "subscriptions", ["status"])
    op.create_index("idx_next_payment", "subscriptions", ["next_payment_date"])

    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "subscription_id",
            sa.Integer(),
            sa.ForeignKey("subscriptions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("billing_date", sa.Date(), nullable=False),
        sa.Column("paid_at", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("amount > 0", name="amount_positive"),
    )
    op.create_index("idx_subscription", "payments", ["subscription_id"])


def downgrade() -> None:
    op.drop_table("payments")
    op.drop_table("subscriptions")
    bind = op.get_bind()
    for enum in (subscription_status, subscription_category, billing_period):
        enum.drop(bind, checkfirst=True)
