"""
FastAPI 公共依赖项
"""

from fastapi import Depends, Header, HTTPException

from .db import session_scope
from .db_models import UserRow
from .settings import settings
from .utils.locale import coerce_locale, set_locale, t
from .utils.security import decode_token


async def use_locale(accept_language: str | None = Header(default=None)):
    """请求级依赖：从 Accept-Language 头解析语言并写入当前上下文。

    后续在该请求中调用 utils.locale.t / get_locale 即可拿到正确语言；
    若请求派生后台线程，需在线程入口处再次 set_locale(get_locale())。
    """
    set_locale(coerce_locale(accept_language))


def get_current_user(authorization: str | None = Header(default=None)) -> dict:
    """请求级依赖：校验 `Authorization: Bearer <access token>` 并返回当前用户。

    失败统一抛 401（缺失/格式错/过期/签名错/用户不存在或被禁用）。
    返回精简 dict，避免 ORM 对象在会话关闭后的 detached 访问。
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail=t("auth.notAuthenticated"))
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = decode_token(token, expected_type="access")
    except Exception as e:  # jwt.ExpiredSignatureError / InvalidTokenError 等
        raise HTTPException(status_code=401, detail=t("auth.invalidToken")) from e

    user_id = payload.get("sub")
    with session_scope() as session:
        user = session.get(UserRow, user_id)
        if user is None or user.status != "active":
            raise HTTPException(status_code=401, detail=t("auth.invalidToken"))
        return {
            "user_id": user.user_id,
            "email": user.email,
            "display_name": user.display_name,
            "status": user.status,
            "email_verified": user.email_verified,
            "is_admin": (user.email or "").lower() in settings.admin_email_set,
        }


def require_verified_user(current: dict = Depends(get_current_user)) -> dict:
    """软门禁：未验证邮箱时拒绝烧钱操作（建图谱/创建/启动模拟），返回 403。

    登录浏览不受限；仅在产生 LLM 成本的入口挂此依赖。
    """
    if not current.get("email_verified"):
        raise HTTPException(status_code=403, detail=t("auth.emailNotVerified"))
    return current


def get_current_admin(current: dict = Depends(get_current_user)) -> dict:
    """运维接口依赖：邮箱不在 admin 白名单则返回 403。"""
    if not current.get("is_admin"):
        raise HTTPException(status_code=403, detail=t("auth.adminRequired"))
    return current
