"""统一错误信封与全局异常处理。

设计目标（消除 4 份重复的 `_error` 与 ~93 处手写信封）：
- 业务错误统一通过 `error_response()` 或抛 `AppError` 产出
  ``{"success": False, "error": <msg>, **extra}`` 信封；
- 请求体校验失败（FastAPI 默认 422）统一映射为 **400 + 业务信封**，
  保持既有「缺必填项返回本地化 400 而非 422」的前端契约；
- 鉴权/授权类 `HTTPException`（401/403/404）**保持 FastAPI 默认 `{"detail": ...}`**，
  不做转换——前端 client.ts 同时兼容 detail/error，且 401 逻辑仅依赖状态码，
  转换无收益且有破坏面。
"""

from typing import Any

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .logger import get_logger
from .settings import settings

logger = get_logger("superfish.api.errors")


def error_response(message: str, status: int = 400, **extra: Any) -> JSONResponse:
    """构造统一错误信封响应，输出 ``{"success": False, "error": message, **extra}``。

    安全门控：调用点常以 ``traceback=traceback.format_exc()`` 传入完整堆栈，
    无条件下发给客户端是信息泄漏面。这里集中处理——堆栈始终落日志，
    仅当 ``settings.debug`` 为真时才放进响应体，生产环境一律丢弃。
    """
    tb = extra.pop("traceback", None)
    if tb:
        logger.error("error_response %s (%s)\n%s", message, status, tb)
        if settings.debug:
            extra["traceback"] = tb
    body: dict[str, Any] = {"success": False, "error": message}
    body.update(extra)
    return JSONResponse(status_code=status, content=body)


class AppError(Exception):
    """业务异常：在 service/repository 层抛出，由全局处理器转为统一信封。

    让深层代码可以「抛错即返回正确响应」，无需把 JSONResponse 一路透传到路由。
    """

    def __init__(self, message: str, status: int = 400, **extra: Any) -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        self.extra = extra


def register_exception_handlers(app: FastAPI) -> None:
    """在应用工厂中注册全局异常处理器。"""

    @app.exception_handler(AppError)
    async def _handle_app_error(_request, exc: AppError) -> JSONResponse:
        return error_response(exc.message, exc.status, **exc.extra)

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(_request, exc: RequestValidationError) -> JSONResponse:
        # 历史行为：缺/错必填项返回本地化 400 信封（而非 FastAPI 默认 422）。
        # 这里把 Pydantic 的结构化校验信息压成一行人类可读文案，状态码降为 400。
        errors = exc.errors()
        if errors:
            first = errors[0]
            loc = ".".join(str(p) for p in first.get("loc", []) if p != "body")
            msg = first.get("msg", "invalid request")
            detail = f"{loc}: {msg}" if loc else msg
        else:
            detail = "invalid request"
        return error_response(detail, status=400)
