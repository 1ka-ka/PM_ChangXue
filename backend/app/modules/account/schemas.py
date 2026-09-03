"""account 模块 Pydantic 模型（技术细节文档 §4 UserBrief/UserFull）。"""

from pydantic import BaseModel, Field, model_validator


class RegisterIn(BaseModel):
    phone: str = Field(min_length=11, max_length=11, pattern=r"^1\d{10}$")
    password: str = Field(min_length=8, max_length=64)
    nickname: str = Field(min_length=1, max_length=20)


class LoginIn(BaseModel):
    phone: str
    password: str


class SmsSendIn(BaseModel):
    phone: str = Field(min_length=11, max_length=11, pattern=r"^1\d{10}$")
    scene: int = Field(ge=2, le=3)  # 2登录 3找回密码（V1.4）


class SmsLoginIn(BaseModel):
    phone: str = Field(min_length=11, max_length=11, pattern=r"^1\d{10}$")
    code: str = Field(min_length=4, max_length=8)


class ResetPasswordIn(BaseModel):
    phone: str = Field(min_length=11, max_length=11, pattern=r"^1\d{10}$")
    code: str = Field(min_length=4, max_length=8)
    new_password: str = Field(min_length=8, max_length=64)


class ProfileUpdateIn(BaseModel):
    nickname: str | None = Field(default=None, min_length=1, max_length=20)
    avatar: str | None = Field(default=None, max_length=255)
    school: str | None = Field(default=None, max_length=50)
    major: str | None = Field(default=None, max_length=50)

    @model_validator(mode="after")
    def at_least_one(self):
        if all(v is None for v in (self.nickname, self.avatar, self.school, self.major)):
            raise ValueError("至少修改一项资料")
        return self


class ThemeIn(BaseModel):
    """主题装扮（V1.6）：整替语义，传 null/空串清除该项。"""

    bg_color: str | None = Field(default=None, max_length=7)  # #RRGGBB
    bg_image: str | None = Field(default=None, max_length=255)  # 仅允许本站 /uploads/ 路径
    theme_color: str | None = Field(default=None, max_length=7)  # #RRGGBB

    @model_validator(mode="after")
    def validate_values(self):
        import re

        hex_re = re.compile(r"^#[0-9a-fA-F]{6}$")
        for name in ("bg_color", "theme_color"):
            v = getattr(self, name)
            if v and not hex_re.match(v):
                raise ValueError(f"{name} 须为 #RRGGBB 颜色值")
        if self.bg_image and not re.match(r"^/uploads/[\w.-]+$", self.bg_image):
            raise ValueError("bg_image 仅允许本站上传图片路径")
        return self


class UserBrief(BaseModel):
    id: int
    nickname: str
    avatar: str | None = None
    school: str = ""
    major: str = ""


class Gratitude(BaseModel):
    week: int = 0
    month: int = 0
    total: int = 0


class UserFull(BaseModel):
    id: int
    nickname: str
    avatar: str | None = None
    school: str = ""
    major: str = ""
    phone: str  # 脱敏后
    gratitude: Gratitude
    credit_balance: int
    is_self: bool = True


class TokenOut(BaseModel):
    token: str
    user: UserBrief | UserFull
