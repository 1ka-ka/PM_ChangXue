"""依赖注入（ARCH §2 core/deps.py）。

- PageParams：分页参数
- get_current_user：JWT → 当前用户（40102 失效 / 40103 封禁）
"""

from fastapi import Depends, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import BizError, ErrCode
from app.core.security import decode_token
from app.models import User

_bearer = HTTPBearer(auto_error=False)


class PageParams:
    """分页参数依赖（技术细节文档 §2.4）：?page=1&page_size=20，page_size 上限 50。"""

    def __init__(
        self,
        page: int = Query(1, ge=1, description="页码，从 1 开始"),
        page_size: int = Query(20, ge=1, le=50, description="每页条数，上限 50"),
    ):
        self.page = page
        self.page_size = page_size

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        return self.page_size


def get_token_payload(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> int:
    """解析 Bearer token → user_id，缺失/无效抛 40102。"""
    if credentials is None or not credentials.credentials:
        raise BizError(ErrCode.TOKEN_INVALID, "未登录或登录已失效")
    uid = decode_token(credentials.credentials)
    if uid is None:
        raise BizError(ErrCode.TOKEN_INVALID, "登录已失效，请重新登录")
    return uid


def get_current_user(
    db: Session = Depends(get_db), uid: int = Depends(get_token_payload)
) -> User:
    """当前登录用户：不存在/已删除→40102，封禁→40103。"""
    user = db.get(User, uid)
    if user is None or user.deleted_at is not None:
        raise BizError(ErrCode.TOKEN_INVALID, "登录已失效，请重新登录")
    if user.status == 1:
        until = user.banned_until.strftime("%Y-%m-%d %H:%M") if user.banned_until else "永久"
        raise BizError(ErrCode.ACCOUNT_BANNED, f"账号已被封禁（{until}）")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    """管理员守卫（管理后台接口统一使用）。"""
    if user.role != 1:
        raise BizError(ErrCode.NOT_ADMIN, "无权限访问")
    return user
