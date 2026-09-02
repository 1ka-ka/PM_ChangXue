"""知识库、感谢值与榜单表（技术细节文档 §3.3）：
knowledge_item / gratitude_stat / rank_snapshot。
"""

from datetime import datetime

from sqlalchemy import (
    DateTime,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, BigInt


class KnowledgeItem(Base):
    __tablename__ = "knowledge_item"

    post_id: Mapped[int] = mapped_column(BigInt, primary_key=True)  # 首次采纳时插入，冲突忽略
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = ({"comment": "知识库收录：仅存 post_id 引用，内容随帖联查不冗余"},)


class GratitudeStat(Base):
    __tablename__ = "gratitude_stat"

    user_id: Mapped[int] = mapped_column(BigInt, primary_key=True)
    period_type: Mapped[int] = mapped_column(SmallInteger, primary_key=True)  # 1周 2月 3累计
    period_key: Mapped[str] = mapped_column(String(10), primary_key=True)  # 2026-W36 / 2026-09 / ALL
    value: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = ({"comment": "感谢值统计：采纳时实时 +30"},)


class RankSnapshot(Base):
    __tablename__ = "rank_snapshot"

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    period_type: Mapped[int] = mapped_column(SmallInteger, nullable=False)  # 1周 2月
    period_key: Mapped[str] = mapped_column(String(10), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    user_id: Mapped[int] = mapped_column(BigInt, nullable=False)
    value: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("period_type", "period_key", "rank", name="uk_period_rank"),
        {"comment": "榜单快照：结算任务写入，榜单公布以此为准（防历史数据变动）"},
    )
