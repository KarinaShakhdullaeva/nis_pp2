import logging
import time

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import text

from app.config import get_settings
from app.deps import DbSession
from app.errors import add_error_handlers
from app.routers import reports, subscriptions

logging.basicConfig(
    level=get_settings().log_level,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("app.requests")

app = FastAPI(
    title="Трекер подписок",
    version="1.0.0",
    description=(
        "Сервер для учёта подписок. Он хранит подписки, считает расходы в месяц "
        "и показывает ближайшие платежи.\n\n"
        "Суммы передаются строкой с двумя знаками после запятой, например `\"299.00\"`. "
        "Все суммы в рублях."
    ),
)
add_error_handlers(app)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    started = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - started) * 1000
    response.headers["X-Process-Time-Ms"] = f"{elapsed_ms:.1f}"
    logger.info(
        "%s %s -> %s (%.1f ms)", request.method, request.url.path, response.status_code, elapsed_ms
    )
    return response


app.include_router(subscriptions.router)
app.include_router(reports.router)


@app.get(
    "/health",
    tags=["Служебное"],
    summary="Проверка работоспособности",
    description="Проверяет, что сервер работает и база данных доступна.",
)
def health(db: DbSession) -> dict[str, str]:
    db.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse("/docs")
