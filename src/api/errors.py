"""Централизованная обработка ошибок FastAPI.

Сервисы могут кидать любые исключения, а здесь мы формируем
корректный HTTP-ответ. Это избавляет эндпоинты от try/except.
"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.core.logging_settings import logger


class AppError(Exception):
    """Базовое бизнес-исключение приложения."""

    status_code = 400

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        if status_code is not None:
            self.status_code = status_code


class NotFoundError(AppError):
    status_code = 404


class ValidationError(AppError):
    status_code = 422


class FileTooLargeError(AppError):
    status_code = 413


class ProcessingError(AppError):
    status_code = 500


def register_exception_handlers(app: FastAPI) -> None:
    """Регистрирует глобальные обработчики исключений."""

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        logger.warning(
            "AppError on {} {}: {}",
            request.method,
            request.url.path,
            exc.message,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.message},
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            "Unhandled error on {} {}: {}",
            request.method,
            request.url.path,
            exc,
            exc_info=True,
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "Внутренняя ошибка сервера"},
        )