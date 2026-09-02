"""帖子与问答表（技术细节文档 §3.2）：
tag / post / post_tag / answer / comment / like_record / favorite。
"""

from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, BigInt


class Tag(Base):
    __tablename__ = "tag"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(20), unique=True)
    sort: Mapped[int] = mapped_column(Integer, default=0)
    enabled: Mapped[int] = mapped_column(SmallInteger, default=1)


class Post(Base):
    __tablename__ = "post"

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    author_id: Mapped[int] = mapped_column(BigInt, nullable=False)
    title: Mapped[str] = mapped_column(String(50), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    images = mapped_column(JSON, nullable=True)  # ["/uploads/x.jpg", ...]
    status: Mapped[int] = mapped_column(SmallInteger, default=0)  # 0待解决 1已解决
    reward: Mapped[int] = mapped_column(Integer, default=0)  # 悬赏档位 0=无
    view_count: Mapped[int] = mapped_column(Integer, default=0)
    answer_count: Mapped[int] = mapped_column(Integer, default=0)
    like_count: Mapped[int] = mapped_column(Integer, default=0)
    last_answer_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    ai_summary: Mapped[str | None] = mapped_column(String(200), default=None)  # V1.2 启用
    ai_answer: Mapped[str | None] = mapped_column(Text, default=None)  # AI 参考回答（V1.3，缓存生成结果）
    ai_answer_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)  # 生成时间
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        Index("idx_post_author", "author_id"),
        Index("idx_post_status", "status"),
        Index("idx_post_last_answer", "last_answer_at"),
        {"comment": "帖子：images 为 JSON 数组；软删见 deleted_at"},
    )


class PostTag(Base):
    __tablename__ = "post_tag"

    post_id: Mapped[int] = mapped_column(
        BigInt, ForeignKey("post.id"), primary_key=True
    )
    tag_id: Mapped[int] = mapped_column(Integer, ForeignKey("tag.id"), primary_key=True)


class Answer(Base):
    __tablename__ = "answer"

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    post_id: Mapped[int] = mapped_column(BigInt, nullable=False)
    author_id: Mapped[int] = mapped_column(BigInt, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_accepted: Mapped[int] = mapped_column(SmallInteger, default=0)
    is_best: Mapped[int] = mapped_column(SmallInteger, default=0)
    like_count: Mapped[int] = mapped_column(Integer, default=0)
    ai_rel_score: Mapped[int | None] = mapped_column(Integer, default=None)  # AI 可靠性评分 0-100（V1.3，异步生成）
    ai_rel_level: Mapped[str | None] = mapped_column(String(10), default=None)  # 高/中/存疑
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        Index("idx_answer_post", "post_id"),
        Index("idx_answer_author", "author_id"),
        Index("idx_answer_accepted", "post_id", "is_accepted"),
        {"comment": "回答：已被采纳不可编辑/删除（40905/40906）"},
    )


class Comment(Base):
    __tablename__ = "comment"

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    target_type: Mapped[int] = mapped_column(SmallInteger, nullable=False)  # 1帖子 2回答
    target_id: Mapped[int] = mapped_column(BigInt, nullable=False)
    author_id: Mapped[int] = mapped_column(BigInt, nullable=False)
    parent_id: Mapped[int | None] = mapped_column(BigInt, default=None)  # NULL=根评论；非空必须指向根评论
    reply_to_user_id: Mapped[int | None] = mapped_column(BigInt, default=None)
    content: Mapped[str] = mapped_column(String(500), nullable=False)
    like_count: Mapped[int] = mapped_column(Integer, default=0)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_comment_target", "target_type", "target_id"),
        {"comment": "双层评论：parent 非 NULL 必须指向根评论（二层封顶）"},
    )


class LikeRecord(Base):
    __tablename__ = "like_record"

    user_id: Mapped[int] = mapped_column(BigInt, primary_key=True)
    target_type: Mapped[int] = mapped_column(SmallInteger, primary_key=True)  # 1帖 2答 3评论
    target_id: Mapped[int] = mapped_column(BigInt, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_like_target", "target_type", "target_id"),
        {"comment": "点赞：联合主键天然幂等"},
    )


class Favorite(Base):
    __tablename__ = "favorite"

    user_id: Mapped[int] = mapped_column(BigInt, primary_key=True)
    target_type: Mapped[int] = mapped_column(SmallInteger, primary_key=True)  # 仅 1帖 2答
    target_id: Mapped[int] = mapped_column(BigInt, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_favorite_target", "target_type", "target_id"),
        {"comment": "收藏：评论不可收藏由服务层校验（40910）"},
    )
