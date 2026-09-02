"""account 业务逻辑（注册/登录/资料/头像/个人主页）。"""

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import BizError, ErrCode
from app.core.security import hash_password, mask_phone, verify_password
from app.core.sensitive import contains_sensitive
from app.models import CreditAccount, CreditLog, GratitudeStat, User
from app.modules.account.schemas import Gratitude, UserBrief, UserFull

# 头像 magic bytes 白名单（技术细节文档 §7.4：不能只信扩展名）
_MAGIC = {
    b"\xff\xd8\xff": "jpg",
    b"\x89PNG": "png",
}


def brief(u: User) -> dict:
    return UserBrief(
        id=u.id, nickname=u.nickname, avatar=u.avatar, school=u.school, major=u.major
    ).model_dump()


def _gratitude_of(db: Session, user_id: int) -> Gratitude:
    week_key = f"{datetime.now().isocalendar().year}-W{datetime.now().isocalendar().week:02d}"
    month_key = datetime.now().strftime("%Y-%m")
    rows = db.execute(
        select(GratitudeStat).where(GratitudeStat.user_id == user_id)
    ).scalars().all()
    vals = {(r.period_type, r.period_key): r.value for r in rows}
    return Gratitude(
        week=vals.get((1, week_key), 0),
        month=vals.get((2, month_key), 0),
        total=vals.get((3, "ALL"), 0),
    )


def register(db: Session, phone: str, password: str, nickname: str) -> tuple[str, User]:
    """注册：事务内建用户 + 积分账户（开户赠 CREDIT_REGISTER）+ 流水。"""
    if contains_sensitive(nickname):
        raise BizError(ErrCode.BAD_REQUEST, "昵称含违禁词")
    exists = db.execute(select(User.id).where(User.phone == phone)).scalar()
    if exists:
        raise BizError(ErrCode.PHONE_EXISTS, "该手机号已注册")
    user = User(phone=phone, password_hash=hash_password(password), nickname=nickname)
    db.add(user)
    db.flush()  # 取 user.id

    # 开户赠积分（S3 将重构为 CreditService.grant，逻辑等价）
    amount = settings.CREDIT_REGISTER
    db.add(CreditAccount(user_id=user.id, balance=amount))
    db.add(
        CreditLog(
            user_id=user.id,
            change=amount,
            balance_after=amount,
            source=1,  # 1=注册赠送
            note="注册开户赠送",
        )
    )
    db.commit()
    return user


def login(db: Session, phone: str, password: str) -> User:
    """登录：校验凭证与封禁状态，更新 last_login_at。"""
    user = db.execute(select(User).where(User.phone == phone)).scalar_one_or_none()
    if user is None or user.deleted_at is not None or not verify_password(
        password, user.password_hash
    ):
        raise BizError(ErrCode.BAD_CREDENTIALS, "账号或密码错误")
    if user.status == 1:
        until = user.banned_until.strftime("%Y-%m-%d %H:%M") if user.banned_until else "永久"
        raise BizError(ErrCode.ACCOUNT_BANNED, f"账号已被封禁（{until}）")
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    return user


def full_info(db: Session, user: User) -> dict:
    """UserFull（本人视角）：脱敏手机号 + 感谢值 + 积分余额。"""
    account = db.get(CreditAccount, user.id)
    return UserFull(
        id=user.id,
        nickname=user.nickname,
        avatar=user.avatar,
        school=user.school,
        major=user.major,
        phone=mask_phone(user.phone),
        gratitude=_gratitude_of(db, user.id),
        credit_balance=account.balance if account else 0,
        is_self=True,
    ).model_dump()


def public_profile(db: Session, viewer: User | None, user_id: int) -> dict:
    """个人主页（公开视角）：credit_balance 仅本人可见。"""
    user = db.get(User, user_id)
    if user is None or user.deleted_at is not None:
        raise BizError(ErrCode.NOT_FOUND, "用户不存在")
    g = _gratitude_of(db, user.id)
    data = brief(user) | {"gratitude": g.model_dump(), "is_self": False}
    if viewer is not None and viewer.id == user_id:
        account = db.get(CreditAccount, user.id)
        data["credit_balance"] = account.balance if account else 0
        data["is_self"] = True
    return data


def update_profile(db: Session, user: User, **fields) -> dict:
    """更新资料：昵称过敏感词校验。"""
    if "nickname" in fields and fields["nickname"] is not None:
        if contains_sensitive(fields["nickname"]):
            raise BizError(ErrCode.BAD_REQUEST, "昵称含违禁词")
    for k, v in fields.items():
        if v is not None:
            setattr(user, k, v)
    db.commit()
    return brief(user)


def save_image(data: bytes, ext: str, *, max_px: int = 1280, prefix: str = "img") -> str:
    """通用图片落盘：magic bytes 校验 + Pillow 压缩，返回 URL 路径（发帖配图/头像共用）。"""
    kind = None
    for magic, name in _MAGIC.items():
        if data.startswith(magic):
            kind = name
            break
    if kind is None or ext.lower().lstrip(".") not in settings.IMAGE_ALLOWED_EXT:
        raise BizError(ErrCode.FILE_INVALID, "仅支持 jpg/png/webp 图片")
    if len(data) > settings.IMAGE_MAX_SIZE_MB * 1024 * 1024:
        raise BizError(ErrCode.FILE_INVALID, f"图片大小不能超过 {settings.IMAGE_MAX_SIZE_MB}MB")

    import io
    import uuid

    from PIL import Image

    img = Image.open(io.BytesIO(data))
    img.thumbnail((max_px, max_px))
    upload_dir = Path(settings.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{prefix}_{uuid.uuid4().hex}.png"
    img.save(upload_dir / filename, "PNG")
    return f"/uploads/{filename}"


def save_avatar(data: bytes, ext: str) -> str:
    """头像落盘：压缩至 256px。"""
    return save_image(data, ext, max_px=256, prefix="avatar")
