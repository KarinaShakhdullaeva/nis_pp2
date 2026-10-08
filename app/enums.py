from enum import StrEnum


class Period(StrEnum):
    WEEK = "week"
    MONTH = "month"
    YEAR = "year"


class Category(StrEnum):
    ENTERTAINMENT = "entertainment"
    MUSIC = "music"
    EDUCATION = "education"
    WORK = "work"
    SOFTWARE = "software"
    HEALTH = "health"
    OTHER = "other"


class Status(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    CANCELLED = "cancelled"


class EventType(StrEnum):
    PAYMENT = "payment"
    TRIAL_END = "trial_end"


class SortField(StrEnum):
    PRICE = "price"
    MONTHLY_PRICE = "monthly_price"
    NEXT_PAYMENT_DATE = "next_payment_date"
    NAME = "name"
    CREATED_AT = "created_at"


class SortOrder(StrEnum):
    ASC = "asc"
    DESC = "desc"
