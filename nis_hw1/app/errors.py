import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("app.errors")


class ErrorDetail(BaseModel):
    location: str
    field: str
    message: str


class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[ErrorDetail] = []


class ErrorResponse(BaseModel):
    error: ErrorBody


class ApiError(Exception):
    status_code = 400
    code = "bad_request"

    def __init__(self, message: str, details: list[ErrorDetail] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or []


class NotFoundError(ApiError):
    status_code = 404
    code = "not_found"


class ConflictError(ApiError):
    status_code = 409
    code = "conflict"


class ValidationApiError(ApiError):
    status_code = 422
    code = "validation_error"

    def __init__(self, field: str, message: str) -> None:
        super().__init__(
            "Ошибка валидации входных данных",
            [ErrorDetail(location="body", field=field, message=message)],
        )


def _error_response(status_code: int, code: str, message: str, details: list[ErrorDetail] | None = None) -> JSONResponse:
    body = ErrorResponse(error=ErrorBody(code=code, message=message, details=details or []))
    return JSONResponse(status_code=status_code, content=body.model_dump())


_MESSAGES: dict[str, str] = {
    "missing": "Обязательное поле",
    "extra_forbidden": "Неизвестное поле",
    "json_invalid": "Некорректный JSON",
    "string_type": "Ожидается строка",
    "string_too_short": "Значение не может быть пустым",
    "string_too_long": "Слишком длинное значение (максимум {max_length} символов)",
    "decimal_parsing": "Ожидается число",
    "decimal_type": "Ожидается число",
    "finite_number": "Ожидается конечное число",
    "int_parsing": "Ожидается целое число",
    "int_type": "Ожидается целое число",
    "date_parsing": "Некорректная дата, ожидается формат ГГГГ-ММ-ДД",
    "date_from_datetime_parsing": "Некорректная дата, ожидается формат ГГГГ-ММ-ДД",
    "date_from_datetime_inexact": "Ожидается дата без времени (ГГГГ-ММ-ДД)",
    "date_type": "Некорректная дата, ожидается формат ГГГГ-ММ-ДД",
    "enum": "Недопустимое значение, ожидается одно из: {expected}",
    "greater_than_equal": "Значение должно быть не меньше {ge}",
    "less_than_equal": "Значение должно быть не больше {le}",
    "model_attributes_type": "Ожидается JSON-объект",
    "dict_type": "Ожидается JSON-объект",
}


def _translate(error: dict[str, Any]) -> str:
    template = _MESSAGES.get(error["type"])
    if template is None:
        return error["msg"]
    ctx = dict(error.get("ctx", {}))
    if "expected" in ctx:
        ctx["expected"] = str(ctx["expected"]).replace(" or ", ", ")
    try:
        return template.format(**ctx)
    except (KeyError, IndexError):
        return error["msg"]


def add_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def handle_api_error(_: Request, exc: ApiError) -> JSONResponse:
        return _error_response(exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            ErrorDetail(
                location=str(err["loc"][0]) if err["loc"] else "",
                field=".".join(str(part) for part in err["loc"][1:]),
                message=_translate(err),
            )
            for err in exc.errors()
        ]
        return _error_response(422, "validation_error", "Ошибка валидации входных данных", details)

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        messages = {404: "Ресурс не найден", 405: "Метод не поддерживается для этого адреса"}
        message = messages.get(exc.status_code, str(exc.detail))
        return _error_response(exc.status_code, "http_error", message)

    @app.exception_handler(Exception)
    async def handle_other_error(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("Необработанная ошибка: %s", exc)
        return _error_response(500, "internal_error", "Внутренняя ошибка сервера")
