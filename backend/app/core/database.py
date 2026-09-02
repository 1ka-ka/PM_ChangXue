"""数据库引擎与会话工厂（ARCH §2 core/database.py）。

开发环境 SQLite / 生产 MySQL，由 DATABASE_URL 切换（技术细节文档 §1.1）。
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    """全部 ORM 模型的基类。"""


def _is_memory_sqlite(url: str) -> bool:
    return url == "sqlite://" or url.endswith(":memory:") or "mode=memory" in url


def _make_engine(url: str):
    if url.startswith("sqlite"):
        kwargs: dict = {"connect_args": {"check_same_thread": False}}
        if _is_memory_sqlite(url):
            # 内存库需保持单连接共享，否则每个会话各建一个空库
            kwargs["poolclass"] = StaticPool
        return create_engine(url, **kwargs)
    # MySQL：连接前 ping 防止使用已被服务端断开的连接
    return create_engine(url, pool_pre_ping=True, pool_recycle=3600)


engine = _make_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖：请求级数据库会话。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
