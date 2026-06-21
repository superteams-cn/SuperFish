"""
鉴权路由（邮箱+密码，纯个人账户，开放注册）。

响应沿用 {"success": ..., "data"/"error": ...} 信封，与前端契约一致。
P0 仅做注册/登录/刷新/获取当前用户；邮箱验证、限流、配额属于 P3 护栏。
"""

import re
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Request

from ..core.deps import get_current_user, use_locale
from ..core.errors import error_response as _error  # 统一错误信封
from ..core.logger import get_logger
from ..core.security import (
    create_access_token,
    create_refresh_token,
    create_reset_token,
    create_verify_token,
    decode_token,
    hash_password,
    password_fingerprint,
    verify_password,
)
from ..core.settings import settings
from ..domain.user import User
from ..repositories.user_repo import UserRepository
from ..schemas.auth import (
    ForgotPasswordRequest,
    LoginCodeRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordCodeRequest,
    ResetPasswordRequest,
    SendCodeRequest,
    VerifyCodeRequest,
    VerifyEmailRequest,
)
from ..utils.locale import t
from ..utils.mailer import send_email_async
from ..utils.rate_limit import check_rate_limit, client_ip
from ..utils.verify_code import (
    TTL_EMAIL_VERIFY,
    generate_code,
    store_code,
    verify_code,
)

logger = get_logger("superfish.auth")

router = APIRouter(dependencies=[Depends(use_locale)])

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_MIN_PASSWORD_LEN = 8


def _public_user(user: User) -> dict:
    return user.to_public_dict()


def _issue_tokens(user_id: str) -> dict:
    return {
        "access_token": create_access_token(user_id),
        "refresh_token": create_refresh_token(user_id),
        "token_type": "bearer",
    }


def _send_verification_email(user_id: str, email: str) -> None:
    """发送邮箱验证邮件：同时附「魔法链接」与「6 位验证码」两种通道。"""
    token = create_verify_token(user_id)
    link = f"{settings.web_base_url}/verify-email?token={token}"
    code = generate_code()
    # 验证码存 Redis(带 TTL)；Redis 不可用时仅链接可用，不阻塞发信
    store_code(f"verify:{user_id}", code, ttl=TTL_EMAIL_VERIFY)
    send_email_async(
        email,
        t("auth.verifyEmailSubject"),
        t("auth.verifyEmailBody", link=link, code=code),
    )
    logger.info(f"已发送邮箱验证邮件: {email}")


_VALID_PURPOSES = {"login", "register", "reset"}


def _send_action_code(email: str, purpose: str) -> None:
    """发送某用途的纯验证码邮件（登录/注册/重置）。"""
    code = generate_code()
    store_code(f"{purpose}:{email}", code)
    send_email_async(email, t("auth.codeEmailSubject"), t("auth.codeEmailBody", code=code))
    logger.info(f"已发送验证码: purpose={purpose} email={email}")


@router.post("/send-code")
def send_code(req: SendCodeRequest, request: Request):
    """统一发送验证码（用途 login/register/reset）。

    反枚举：始终返回成功，仅在合适条件下真正发码——
    login/reset 仅对已存在的活跃账户发，register 仅对未注册邮箱发。
    """
    email = (req.email or "").strip().lower()
    purpose = (req.purpose or "").strip()
    if not _EMAIL_RE.match(email):
        return _error(t("auth.invalidEmail"), 400)
    if purpose not in _VALID_PURPOSES:
        return _error(t("auth.invalidPurpose"), 400)

    # 限流：IP + 邮箱(按用途) 双维度，防轰炸/枚举
    if not check_rate_limit(
        f"auth:sendcode:ip:{client_ip(request)}", 10, 600
    ) or not check_rate_limit(f"auth:sendcode:{purpose}:email:{email}", 5, 600):
        return _error(t("auth.rateLimited"), 429)

    user = UserRepository.get_by_email(email)
    exists = user is not None and user.is_active

    should_send = (purpose in ("login", "reset") and exists) or (
        purpose == "register" and not exists
    )
    if should_send:
        _send_action_code(email, purpose)

    return {"success": True, "data": {"message": t("auth.codeSent")}}


@router.post("/register")
def register(req: RegisterRequest, request: Request):
    """注册新账户（注册即验证：需带邮箱验证码）。建号即 email_verified=True。"""
    email = (req.email or "").strip().lower()
    password = req.password or ""
    code = (req.code or "").strip()

    if not _EMAIL_RE.match(email):
        return _error(t("auth.invalidEmail"), 400)
    if len(password) < _MIN_PASSWORD_LEN:
        return _error(t("auth.passwordTooShort"), 400)

    # 限流：按 IP 防注册刷量
    if not check_rate_limit(
        f"auth:register:ip:{client_ip(request)}", settings.rate_limit_register_per_hour, 3600
    ):
        return _error(t("auth.rateLimited"), 429)

    # 邮箱唯一性先行（已注册给明确提示，不消费验证码）
    if UserRepository.email_exists(email):
        return _error(t("auth.emailTaken"), 409)

    # 校验注册验证码（消费一次性）
    if not verify_code(f"register:{email}", code):
        return _error(t("auth.invalidVerifyCode"), 400)

    now = datetime.now().isoformat()
    user_id = "user_" + uuid.uuid4().hex[:16]
    display_name = (req.display_name or "").strip() or email.split("@")[0]

    try:
        user = UserRepository.create(
            user_id=user_id,
            email=email,
            password_hash=hash_password(password),
            display_name=display_name,
            email_verified=True,  # 验证码已证明邮箱归属
            created_at=now,
            updated_at=now,
        )
    except ValueError:
        # 二次确认唯一失败（TOCTOU 竞态；唯一索引兜底）
        return _error(t("auth.emailTaken"), 409)
    data = {"user": _public_user(user), **_issue_tokens(user.user_id)}

    logger.info(f"新用户注册(已验证): {email}")
    return {"success": True, "data": data}


@router.post("/login")
def login(req: LoginRequest, request: Request):
    """邮箱+密码登录。"""
    email = (req.email or "").strip().lower()
    password = req.password or ""
    if not email or not password:
        return _error(t("auth.missingCredentials"), 400)

    # 限流：IP 与邮箱双维度，挡暴力撞库
    ip = client_ip(request)
    if not check_rate_limit(
        f"auth:login:ip:{ip}", settings.rate_limit_login_per_min, 60
    ) or not check_rate_limit(f"auth:login:email:{email}", settings.rate_limit_login_per_min, 60):
        return _error(t("auth.rateLimited"), 429)

    user = UserRepository.get_by_email(email)
    # 无论用户是否存在都走一次校验，降低用户枚举差异（错误信息保持一致）
    ok = user is not None and verify_password(password, user.password_hash)
    if not ok:
        return _error(t("auth.invalidCredentials"), 401)
    assert user is not None  # ok 为真即已排除 None（供类型收窄）
    if not user.is_active:
        return _error(t("auth.accountDisabled"), 403)
    data = {"user": _public_user(user), **_issue_tokens(user.user_id)}

    return {"success": True, "data": data}


@router.post("/login-code")
def login_code(req: LoginCodeRequest, request: Request):
    """验证码登录（无密码）。验证码仅对已存在账户发放，校验通过即签发令牌。"""
    email = (req.email or "").strip().lower()
    code = (req.code or "").strip()
    if not _EMAIL_RE.match(email):
        return _error(t("auth.invalidEmail"), 400)

    # 限流：邮箱维度防爆破
    if not check_rate_limit(f"auth:logincode:email:{email}", 5, 600):
        return _error(t("auth.rateLimited"), 429)

    if not verify_code(f"login:{email}", code):
        return _error(t("auth.invalidVerifyCode"), 400)

    user = UserRepository.get_by_email(email)
    if user is None or not user.is_active:
        return _error(t("auth.invalidCredentials"), 401)
    # 验证码登录已证明邮箱归属，顺带置为已验证
    if not user.email_verified:
        UserRepository.mark_verified(user.user_id)
        user.email_verified = True  # 同步快照，使返回的 public 反映已验证
    data = {"user": _public_user(user), **_issue_tokens(user.user_id)}

    return {"success": True, "data": data}


@router.post("/refresh")
def refresh(req: RefreshRequest):
    """用 refresh token 换发新的 access/refresh token。"""
    token = (req.refresh_token or "").strip()
    if not token:
        return _error(t("auth.missingRefreshToken"), 400)
    try:
        payload = decode_token(token, expected_type="refresh")
    except Exception:
        return _error(t("auth.invalidToken"), 401)

    user_id = str(payload.get("sub") or "")
    user = UserRepository.get_by_id(user_id)
    if user is None or not user.is_active:
        return _error(t("auth.invalidToken"), 401)
    data = _issue_tokens(user.user_id)

    return {"success": True, "data": data}


@router.post("/forgot-password")
def forgot_password(req: ForgotPasswordRequest, request: Request):
    """申请重置密码：向邮箱发送重置链接。

    无论邮箱是否存在都返回成功，避免用户枚举。开发桩下邮件打印到后端日志。
    """
    email = (req.email or "").strip().lower()
    if not _EMAIL_RE.match(email):
        return _error(t("auth.invalidEmail"), 400)

    # 限流：IP + 邮箱，防找回密码邮件轰炸
    if not check_rate_limit(
        f"auth:forgot:ip:{client_ip(request)}", settings.rate_limit_forgot_per_hour, 3600
    ) or not check_rate_limit(
        f"auth:forgot:email:{email}", settings.rate_limit_forgot_per_hour, 3600
    ):
        return _error(t("auth.rateLimited"), 429)

    user = UserRepository.get_by_email(email)
    if user is not None and user.is_active:
        token = create_reset_token(user.user_id, user.password_hash)
        link = f"{settings.web_base_url}/reset-password?token={token}"
        send_email_async(
            user.email,
            t("auth.resetEmailSubject"),
            t("auth.resetEmailBody", link=link),
        )
        logger.info(f"已发送重置密码邮件: {email}")

    return {"success": True, "data": {"message": t("auth.resetEmailSent")}}


@router.post("/reset-password")
def reset_password(req: ResetPasswordRequest):
    """凭重置令牌设置新密码。令牌过期/被改密失效/格式错均返回 400。"""
    token = (req.token or "").strip()
    new_password = req.new_password or ""
    if not token:
        return _error(t("auth.invalidResetToken"), 400)
    if len(new_password) < _MIN_PASSWORD_LEN:
        return _error(t("auth.passwordTooShort"), 400)

    try:
        payload = decode_token(token, expected_type="reset")
    except Exception:
        return _error(t("auth.invalidResetToken"), 400)

    user = UserRepository.get_by_id(str(payload.get("sub") or ""))
    # 指纹不符 = 密码已改过（旧链接） → 失效
    if (
        user is None
        or not user.is_active
        or payload.get("pwf") != password_fingerprint(user.password_hash)
    ):
        return _error(t("auth.invalidResetToken"), 400)
    UserRepository.set_password(user.user_id, hash_password(new_password))

    logger.info(f"密码已重置: user={payload.get('sub')}")
    return {"success": True, "data": {"message": t("auth.resetSuccess")}}


@router.post("/reset-password-code")
def reset_password_code(req: ResetPasswordCodeRequest):
    """凭验证码重置密码（与链接重置并存）。验证码仅对已存在账户发放。"""
    email = (req.email or "").strip().lower()
    code = (req.code or "").strip()
    new_password = req.new_password or ""
    if not _EMAIL_RE.match(email):
        return _error(t("auth.invalidEmail"), 400)
    if len(new_password) < _MIN_PASSWORD_LEN:
        return _error(t("auth.passwordTooShort"), 400)

    if not verify_code(f"reset:{email}", code):
        return _error(t("auth.invalidVerifyCode"), 400)

    user = UserRepository.get_by_email(email)
    if user is None or not user.is_active:
        return _error(t("auth.invalidVerifyCode"), 400)
    UserRepository.set_password(user.user_id, hash_password(new_password))

    logger.info(f"密码已重置(验证码): {email}")
    return {"success": True, "data": {"message": t("auth.resetSuccess")}}


@router.post("/verify-email")
def verify_email(req: VerifyEmailRequest):
    """凭验证令牌确认邮箱。令牌过期/格式错返回 400；已验证则幂等返回成功。"""
    token = (req.token or "").strip()
    if not token:
        return _error(t("auth.invalidVerifyToken"), 400)
    try:
        payload = decode_token(token, expected_type="verify")
    except Exception:
        return _error(t("auth.invalidVerifyToken"), 400)

    user = UserRepository.get_by_id(str(payload.get("sub") or ""))
    if user is None or not user.is_active:
        return _error(t("auth.invalidVerifyToken"), 400)
    UserRepository.mark_verified(user.user_id)

    logger.info(f"邮箱已验证: user={payload.get('sub')}")
    return {"success": True, "data": {"message": t("auth.verifySuccess")}}


@router.post("/verify-email-code")
def verify_email_code(req: VerifyCodeRequest, current=Depends(get_current_user)):
    """凭 6 位验证码确认邮箱（需登录，验证码绑定当前用户）。

    与魔法链接并存，校验同一件事。按用户限流防爆破；已验证则幂等返回成功。
    """
    if current.get("email_verified"):
        return {"success": True, "data": {"message": t("auth.alreadyVerified")}}

    # 限流：每用户 10 分钟最多 5 次尝试，挡 6 位码爆破
    if not check_rate_limit(f"auth:verifycode:user:{current['user_id']}", 5, 600):
        return _error(t("auth.rateLimited"), 429)

    code = (req.code or "").strip()
    if not verify_code(f"verify:{current['user_id']}", code):
        return _error(t("auth.invalidVerifyCode"), 400)

    user = UserRepository.get_by_id(current["user_id"])
    if user is None or not user.is_active:
        return _error(t("auth.invalidVerifyCode"), 400)
    UserRepository.mark_verified(user.user_id)

    logger.info(f"邮箱已验证(验证码): user={current['user_id']}")
    return {"success": True, "data": {"message": t("auth.verifySuccess")}}


@router.post("/resend-verification")
def resend_verification(request: Request, current=Depends(get_current_user)):
    """重发邮箱验证邮件（需登录）。已验证则直接返回成功，不再发信。"""
    if current.get("email_verified"):
        return {"success": True, "data": {"message": t("auth.alreadyVerified")}}

    if not check_rate_limit(
        f"auth:resend:user:{current['user_id']}", settings.rate_limit_resend_per_hour, 3600
    ):
        return _error(t("auth.rateLimited"), 429)

    try:
        _send_verification_email(current["user_id"], current["email"])
    except Exception as e:
        logger.warning(f"重发验证邮件失败: {current['email']} err={e}")
    return {"success": True, "data": {"message": t("auth.verifyEmailSent")}}


@router.get("/me")
def me(current=Depends(get_current_user)):
    """获取当前登录用户信息。"""
    return {"success": True, "data": current}
