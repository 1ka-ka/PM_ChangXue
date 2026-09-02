"""安全组件：密码哈希（bcrypt）与 JWT 签发校验（技术细节文档 §7.1/§7.2）。"""

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import settings

_JWT_ALG = "HS256"


def hash_password(plain: str) -> str:
    """bcrypt 哈希（cost=12）。"""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def create_token(user_id: int) -> str:
    """签发访问令牌：负载仅含 uid 与过期时间（不携带角色，角色实时查库）。"""
    payload = {
        "uid": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(hours=settings.ACCESS_TOKEN_EXPIRE_HOURS),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=_JWT_ALG)


def decode_token(token: str) -> int | None:
    """校验并解析令牌，返回 user_id；无效/过期返回 None（不抛错）。"""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[_JWT_ALG])
    except jwt.PyJWTError:
        return None
    uid = payload.get("uid")
    if not isinstance(uid, int):
        return None
    return uid


def mask_phone(phone: str) -> str:
    """手机号脱敏：保留前 3 后 4。"""
    return f"{phone[:3]}****{phone[-4:]}" if len(phone) == 11 else phone
