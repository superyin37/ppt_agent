from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from .exceptions import AppError
import logging
import time

logger = logging.getLogger(__name__)


def setup_middleware(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        logger.warning(
            f"AppError: {exc.error_code} | {exc.message} | "
            f"path={request.url.path} | retryable={exc.retryable}"
        )
        return JSONResponse(
            status_code=exc.http_status,
            content={
                "success": False,
                "error": exc.message,
                "error_code": exc.error_code,
                "detail": exc.detail,
            }
        )

    @app.exception_handler(Exception)
    async def generic_error_handler(request: Request, exc: Exception):
        logger.error(f"Unhandled exception: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": "服务内部错误",
                "error_code": "INTERNAL_ERROR",
                "detail": {},
            }
        )

    @app.middleware("http")
    async def request_logger(request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000
        logger.info(
            f"{request.method} {request.url.path} "
            f"→ {response.status_code} ({duration_ms:.1f}ms)"
        )
        # 前端 JS/CSS 开发期间禁用缓存
        if request.url.path.startswith("/app/") and request.url.path.endswith((".js", ".css")):
            response.headers["Cache-Control"] = "no-store"
        return response
