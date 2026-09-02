"""通知、治理与埋点表（技术细节文档 §3.4）：
notification / report / admin_action_log / tracking_event / app_config。
"""

from datetime import datetime

from sqlalchemy import (
    DateTime,
    Index,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, BigInt


class Notification(Base):
    __tablename__ = "notification"

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInt, nullable=False)  # 接收者
    type: Mapped[int] = mapped_column(SmallInteger, nullable=False)  # 1被回答 2被评论 3被回复 4被采纳 5被点赞
    actor_id: Mapped[int] = mapped_column(BigInt, nullable=False)
    target_type: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    target_id: Mapped[int] = mapped_column(BigInt, nullable=False)
    is_read: Mapped[int] = mapped_column(SmallInteger, default=0)
    invalid: Mapped[int] = mapped_column(SmallInteger, default=0)  # 1=原内容已删除
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_user_read", "user_id", "is_read"),
        {"comment": "站内通知：五类互动"},
    )


class Report(Base):
    __tablename__ = "report"

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    reporter_id: Mapped[int] = mapped_column(BigInt, nullable=False)
    target_type: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    target_id: Mapped[int] = mapped_column(BigInt, nullable=False)
    reason: Mapped[int] = mapped_column(SmallInteger, nullable=False)  # 1垃圾广告 2人身攻击 3色情低俗 4违法违规 5其他
    detail: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[int] = mapped_column(SmallInteger, default=0)  # 0待处理 1已处置 2驳回
    handled_by: Mapped[int | None] = mapped_column(BigInt, default=None)
    result: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("reporter_id", "target_type", "target_id", name="uk_dedup"),  # 举报去重
        Index("idx_report_status", "status"),
        {"comment": "举报：唯一键去重（40903）"},
    )


class AdminActionLog(Base):
    __tablename__ = "admin_action_log"

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    admin_id: Mapped[int] = mapped_column(BigInt, nullable=False)
    action: Mapped[int] = mapped_column(SmallInteger, nullable=False)  # 1删帖 2删回答 3删评论 4封号 5解封 6追回积分 7驳回举报 8恢复内容
    target_type: Mapped[int | None] = mapped_column(SmallInteger, default=None)
    target_id: Mapped[int | None] = mapped_column(BigInt, default=None)
    reason: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = ({"comment": "管理员操作日志：全部处置留痕"},)


class TrackingEvent(Base):
    __tablename__ = "tracking_event"

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(BigInt, default=None)  # 未登录可为 NULL
    event_name: Mapped[str] = mapped_column(String(50), nullable=False)
    props = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_event_time", "event_name", "created_at"),
        {"comment": "埋点事件：批量异步落库，失败不影响业务"},
    )


class AppConfig(Base):
    __tablename__ = "app_config"

    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    value = mapped_column(JSON, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = ({"comment": "运行时配置：覆盖 env 默认值（积分分值/阈值等）"},)
