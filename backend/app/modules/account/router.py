"""account 路由：接口 1-3、5-8、8b（技术细节文档 §5.1）。"""

from pathlib import Path

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.response import ok
from app.core.security import create_token, decode_token
from app.models import User
from app.modules.account import service
from app.modules.account.schemas import (
    LoginIn,
    ProfileUpdateIn,
    RegisterIn,
    ResetPasswordIn,
    SmsLoginIn,
    SmsSendIn,
    ThemeIn,
)

router = APIRouter()
_bearer = HTTPBearer(auto_error=False)


def optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User | None:
    """可选登录态：公开接口带 token 时识别身份，无效 token 不报错（降级匿名）。"""
    if credentials is None or not credentials.credentials:
        return None
    uid = decode_token(credentials.credentials)
    if uid is None:
        return None
    user = db.get(User, uid)
    if user is None or user.deleted_at is not None or user.status == 1:
        return None
    return user


@router.post("/auth/register")
def register(body: RegisterIn, db: Session = Depends(get_db)):
    user = service.register(db, body.phone, body.password, body.nickname)
    return ok({"token": create_token(user.id), "user": service.full_info(db, user)})


@router.post("/auth/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = service.login(db, body.phone, body.password)
    return ok({"token": create_token(user.id), "user": service.brief(user)})


# ---- 短信验证码（V1.4）：发送 / 短信登录 / 找回密码 ----


@router.post("/auth/sms/send")
def sms_send(body: SmsSendIn, db: Session = Depends(get_db)):
    return ok(service.sms_send(db, body.phone, body.scene))


@router.post("/auth/sms/login")
def sms_login(body: SmsLoginIn, db: Session = Depends(get_db)):
    user = service.sms_login(db, body.phone, body.code)
    return ok({"token": create_token(user.id), "user": service.brief(user)})


@router.post("/auth/reset-password")
def reset_password(body: ResetPasswordIn, db: Session = Depends(get_db)):
    service.reset_password(db, body.phone, body.code, body.new_password)
    return ok(None)


@router.get("/auth/me")
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(service.full_info(db, user))


@router.put("/account/profile")
def update_profile(
    body: ProfileUpdateIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return ok(service.update_profile(db, user, **body.model_dump(exclude_none=True)))


@router.post("/account/avatar")
async def upload_avatar(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    data = await file.read()
    ext = Path(file.filename or "").suffix
    url = service.save_avatar(data, ext)
    user.avatar = url
    db.commit()
    return ok({"url": url})


@router.get("/account/users/{user_id}")
def user_profile(
    user_id: int,
    viewer: User | None = Depends(optional_user),
    db: Session = Depends(get_db),
):
    return ok(service.public_profile(db, viewer, user_id))


@router.get("/account/theme")
def theme(
    user_id: int | None = None,
    viewer: User | None = Depends(optional_user),
    db: Session = Depends(get_db),
):
    """用户装扮配置（V1.6 起生效）：?user_id= 指定用户（公开）；缺省为当前登录用户。"""
    if user_id is None:
        return ok({"theme": viewer.theme_config if viewer else None})
    return ok({"theme": service.get_theme(db, user_id)})


@router.put("/account/theme")
def update_theme(
    body: ThemeIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """设置本人装扮（V1.6）：整替语义，全空恢复默认。"""
    theme = service.update_theme(db, user, body.bg_color, body.bg_image, body.theme_color)
    return ok({"theme": theme})
