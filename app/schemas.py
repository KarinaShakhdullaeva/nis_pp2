from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Self

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, computed_field, model_validator
from pydantic_core import PydanticCustomError

from app.enums import Category, EventType, Period, Status
from app.services.billing import CENT, monthly_price

MIN_DATE = date(2000, 1, 1)
MAX_DATE = date(2100, 12, 31)
MAX_AMOUNT = Decimal("9999999999.99")


def _validate_money(value: Decimal) -> Decimal:
    if not value.is_finite():
        raise PydanticCustomError("money_invalid", "Сумма должна быть числом")
    if value <= 0:
        raise PydanticCustomError("money_not_positive", "Сумма должна быть больше 0")
    if value > MAX_AMOUNT:
        raise PydanticCustomError("money_too_large", "Сумма слишком большая (максимум 9999999999.99)")
    if value != value.quantize(CENT):
        raise PydanticCustomError("money_precision", "Не больше двух знаков после запятой")
    return value.quantize(CENT)


def _validate_date(value: date) -> date:
    if not MIN_DATE <= value <= MAX_DATE:
        raise PydanticCustomError(
            "date_out_of_range", "Дата должна быть в диапазоне от 2000-01-01 до 2100-12-31"
        )
    return value


Money = Annotated[Decimal, AfterValidator(_validate_money), Field(examples=["299.00"])]
ValidDate = Annotated[date, AfterValidator(_validate_date)]
Name = Annotated[str, Field(min_length=1, max_length=100, examples=["Яндекс Плюс"])]

_INPUT_CONFIG = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SubscriptionCreate(BaseModel):
    model_config = _INPUT_CONFIG

    name: Name
    price: Money = Field(description="Стоимость за один период, ₽")
    period: Period = Field(description="Периодичность списания")
    next_payment_date: ValidDate = Field(description="Дата следующего списания")
    category: Category = Field(default=Category.OTHER, description="Категория")
    trial_end_date: ValidDate | None = Field(default=None, description="Дата окончания пробного периода")


# Статус меняется отдельной ручкой
class SubscriptionUpdate(BaseModel):
    model_config = _INPUT_CONFIG

    name: Name | None = None
    price: Money | None = None
    period: Period | None = None
    next_payment_date: ValidDate | None = None
    category: Category | None = None
    trial_end_date: ValidDate | None = Field(default=None, description="null удаляет пробный период")

    @model_validator(mode="after")
    def _check_fields(self) -> Self:
        if not self.model_fields_set:
            raise PydanticCustomError("empty_update", "Передайте хотя бы одно поле для изменения")
        for field in sorted(self.model_fields_set - {"trial_end_date"}):
            if getattr(self, field) is None:
                raise PydanticCustomError(
                    "null_not_allowed", "Поле '{field}' не может быть null", {"field": field}
                )
        return self


class StatusUpdate(BaseModel):
    model_config = _INPUT_CONFIG

    status: Status


class SubscriptionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    price: Decimal
    period: Period
    next_payment_date: date
    category: Category
    status: Status
    trial_end_date: date | None
    created_at: datetime
    updated_at: datetime

    @computed_field(description="Стоимость в пересчёте на месяц, ₽")
    @property
    def monthly_price(self) -> Decimal:
        return monthly_price(self.price, self.period)


# Если тело не передать, сумма будет равна цене подписки, а дата оплаты сегодняшней
class PaymentCreate(BaseModel):
    model_config = _INPUT_CONFIG

    paid_at: ValidDate | None = Field(default=None, description="Дата оплаты, по умолчанию сегодня")
    amount: Money | None = Field(default=None, description="Сумма, по умолчанию текущая стоимость")


class PaymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    subscription_id: int
    amount: Decimal
    billing_date: date = Field(description="За какую дату списания внесён платёж")
    paid_at: date
    created_at: datetime


class PaymentResult(BaseModel):
    payment: PaymentRead
    subscription: SubscriptionRead = Field(description="Подписка с уже сдвинутой датой списания")


class PaymentHistory(BaseModel):
    subscription_id: int
    count: int
    total_paid: Decimal
    items: list[PaymentRead]


class CategoryTotalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    category: Category
    total: Decimal
    count: int


class MonthlySummaryRead(BaseModel):
    currency: str
    total: Decimal
    active_subscriptions: int
    by_category: list[CategoryTotalRead]


class UpcomingItem(BaseModel):
    subscription_id: int
    name: str
    category: Category
    type: EventType
    due_date: date
    days_left: int = Field(description="Сколько дней осталось. У просроченных число отрицательное")
    amount: Decimal
    overdue: bool


class UpcomingRead(BaseModel):
    currency: str
    days: int
    date_from: date
    date_to: date
    total: Decimal = Field(description="Сумма списаний в окне, включая просроченные")
    items: list[UpcomingItem]
