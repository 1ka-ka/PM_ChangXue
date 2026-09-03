"""私信表（V1.7）：dm_conversation / dm_message（一对一私信，游标已读）。"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, BigInt


class DmConversation(Base):
    __tablename__ = "dm_conversation"

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    # 约定 user_a_id < user_b_id，保证同一对用户唯一会话
    user_a_id: Mapped[int] = mapped_column(BigInt, nullable=False)
    user_b_id: Mapped[int] = mapped_column(BigInt, nullable=False)
    a_last_read_id: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)  # A 已读游标（消息 id）
    b_last_read_id: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    last_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)  # 冗余最新消息 id（列表联查）
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now, onupdate=datetime.now
    )

    __table_args__ = (
        UniqueConstraint("user_a_id", "user_b_id", name="uk_dm_user_pair"),
        {"comment": "私信会话：一对用户唯一（a<b），游标式已读"},
    )


class DmMessage(Base):
    __tablename__ = "dm_message"

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(
        BigInt, ForeignKey("dm_conversation.id"), nullable=False, index=True
    )
    sender_id: Mapped[int] = mapped_column(BigInt, nullable=False)
    content: Mapped[str] = mapped_column(String(500), nullable=False)  # 纯文本 1-500 字
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)

    __table_args__ = ({"comment": "私信消息：纯文本，已读由会话游标计算"},)
