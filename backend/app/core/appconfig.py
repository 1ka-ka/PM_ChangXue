"""app_config 运行时配置读写（技术细节文档 §3.4）。

优先级：app_config 表 > env 默认值。
读取失败/键不存在时回退 settings 默认值（不抛错，保证业务可用）。
"""

from sqlalchemy import select

from app.core.config import settings
from app.core.database import SessionLocal
from app.models import AppConfig


def get_config(key: str, default):
    """读取运行时配置；表无此键或读库失败时返回 default。"""
    try:
        with SessionLocal() as db:
            row = db.get(AppConfig, key)
            if row is None:
                return default
            return row.value
    except Exception:
        return default


def set_config(key: str, value) -> None:
    """写入运行时配置（管理员调整积分参数等场景）。"""
    with SessionLocal() as db:
        row = db.get(AppConfig, key)
        if row is None:
            db.add(AppConfig(key=key, value=value))
        else:
            row.value = value
        db.commit()


def get_credit(name: str) -> int:
    """读取积分类参数的便捷方法：app_config('credit.xxx') > settings 默认。"""
    mapping = {
        "register": settings.CREDIT_REGISTER,
        "daily_login": settings.CREDIT_DAILY_LOGIN,
        "accept": settings.CREDIT_ACCEPT,
        "daily_cap": settings.CREDIT_DAILY_CAP,
    }
    if name not in mapping:
        raise KeyError(f"未知积分参数: {name}")
    return get_config(f"credit.{name}", mapping[name])
