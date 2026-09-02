"""用户与账号表（技术细节文档 §3.1）：user / credit_account / credit_log。"""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, SmallInteger, String, func
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, BigInt


class User(Base):
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    phone: Mapped[str] = mapped_column(String(20), unique=True)
    password_hash: Mapped[str] = mapped_column(String(128))
    nickname: Mapped[str] = mapped_column(String(20))
    avatar: Mapped[str | None] = mapped_column(String(255), default=None)
    school: Mapped[str] = mapped_column(String(50), default="")
    major: Mapped[str] = mapped_column(String(50), default="")
    theme_config = mapped_column(JSON, nullable=True)  # P2 个性化装扮配置（P0 恒 NULL）
    role: Mapped[int] = mapped_column(SmallInteger, default=0)  # 0普通用户 1管理员
    status: Mapped[int] = mapped_column(SmallInteger, default=0)  # 0正常 1封禁
    banned_until: Mapped[datetime | None] = mapped_column(DateTime, default=None)  # NULL=永久
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_school", "school"),
        Index("idx_major", "major"),
        {"comment": "用户表：手机号为主账号（MVP 无认证）"},
    )


class CreditAccount(Base):
    __tablename__ = "credit_account"

    user_id: Mapped[int] = mapped_column(
        BigInt, ForeignKey("user.id"), primary_key=True
    )
    balance: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (
        CheckConstraint("balance >= 0", name="ck_balance_nonnegative"),
        {"comment": "积分账户：balance 恒非负，服务层行锁防透支"},
    )


class CreditLog(Base):
    __tablename__ = "credit_log"

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInt, nullable=False)
    change: Mapped[int] = mapped_column(Integer, nullable=False)  # 正=产出 负=消耗
    balance_after: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[int] = mapped_column(SmallInteger, nullable=False)  # 见 CreditSource
    ref_type: Mapped[int | None] = mapped_column(SmallInteger, default=None)
    ref_id: Mapped[int | None] = mapped_column(BigInt, default=None)
    note: Mapped[str] = mapped_column(String(100), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_user_date", "user_id", "created_at"),  # 日封顶统计
        {"comment": "积分流水：全量记录，balance_after 保证连续性"},
    )
