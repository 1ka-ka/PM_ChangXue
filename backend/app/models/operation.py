"""系统账号自动运营表（V1.13）：operation_log。

运营账号本身复用 user 表（is_op=1 内部标记，任何 API 不暴露——与真人地位等同）；
operation_log 记录每个运营动作（成功与跳过均留痕），供当日配额统计与管理后台展示。
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, SmallInteger, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, BigInt


class OperationLog(Base):
    __tablename__ = "operation_log"

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(BigInt, default=None)  # 动作执行账号（补贴/建号可空）
    action: Mapped[int] = mapped_column(SmallInteger, nullable=False)  # 1-8 见 operation/service.py
    ok: Mapped[int] = mapped_column(SmallInteger, default=1)  # 1成功 0跳过/失败（原因见 detail）
    target_type: Mapped[int | None] = mapped_column(SmallInteger, default=None)
    target_id: Mapped[int | None] = mapped_column(BigInt, default=None)
    detail: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, server_default=func.now())

    __table_args__ = (
        Index("idx_op_date", "created_at"),  # 当日配额统计
        Index("idx_op_user", "user_id", "id"),
        {"comment": "系统运营动作日志：配额统计（action 1-6）+ 后台展示"},
    )
