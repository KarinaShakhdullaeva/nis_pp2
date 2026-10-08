from datetime import date, datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import Depends
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db


def get_today() -> date:
    return datetime.now(ZoneInfo(get_settings().app_timezone)).date()


DbSession = Annotated[Session, Depends(get_db)]
Today = Annotated[date, Depends(get_today)]
