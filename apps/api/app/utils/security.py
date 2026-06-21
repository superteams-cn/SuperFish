"""
鉴权安全工具：密码哈希（PBKDF2-SHA256，零新依赖）+ JWT 签发/校验。

- 密码哈希用 stdlib hashlib.pbkdf2_hmac，存储格式：
  pbkdf2_sha256$<iterations>$<b64 salt>$<b64 hash>
  迭代次数随存储字符串走，便于将来无痛提升强度。
- JWT 用 PyJWT，密钥/有效期来自 settings（上线务必用环境变量覆盖 jwt_secret）。
"""

import base64
import hashlib
import hmac
import secrets
import time

import jwt

from ..settings import settings

_PBKDF2_ALGO = "pbkdf2_sha256"
_PBKDF2_ITER = 600_000


def hash_password(password: str) -> str:
    """生成带盐的 PBKDF2 哈希串。"""
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITER)
    return (
        f"{_PBKDF2_ALGO}${_PBKDF2_ITER}$"
        f"{base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"
    )


def verify_password(password: str, stored: str) -> bool:
    """常数时间比对密码与存储哈希；任何解析异常都视为不通过。"""
    try:
        algo, iter_s, salt_b64, hash_b64 = stored.split("$")
        if algo != _PBKDF2_ALGO:
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iter_s))
        return hmac.compare_digest(dk, expected)
    except Exception:
        return False


def _make_token(user_id: str, ttl_seconds: int, token_type: str) -> str:
    now = int(time.time())
    payload = {
        "sub": user_id,
        "type": token_type,
        "iat": now,
        "exp": now + ttl_seconds,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(user_id: str) -> str:
    return _make_token(user_id, settings.jwt_access_ttl_min * 60, "access")


def create_refresh_token(user_id: str) -> str:
    return _make_token(user_id, settings.jwt_refresh_ttl_days * 86400, "refresh")


def create_verify_token(user_id: str) -> str:
    """签发邮箱验证令牌（type=verify）。点击链接后置 email_verified=True。"""
    return _make_token(user_id, settings.jwt_verify_ttl_min * 60, "verify")


def password_fingerprint(password_hash: str) -> str:
    """由当前密码哈希派生短指纹，写入重置令牌。

    改密后指纹变化 → 旧重置链接自动失效（即便未到 exp），实现一次性效果。
    """
    return hashlib.sha256(password_hash.encode("utf-8")).hexdigest()[:16]


def create_reset_token(user_id: str, password_hash: str) -> str:
    now = int(time.time())
    payload = {
        "sub": user_id,
        "type": "reset",
        "iat": now,
        "exp": now + settings.jwt_reset_ttl_min * 60,
        "pwf": password_fingerprint(password_hash),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str, expected_type: str = "access") -> dict:
    """解码并校验 JWT；类型不符或过期/签名错误均抛 jwt 异常，由调用方转 401。"""
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    if payload.get("type") != expected_type:
        raise jwt.InvalidTokenError("token type mismatch")
    return payload
