"""S1 测试：app_config 运行时配置封装。"""

from app.core import appconfig
from app.core.database import SessionLocal
from app.models import AppConfig


def test_default_fallback():
    """键不存在时回退默认值。"""
    assert appconfig.get_config("no.such.key", 42) == 42


def test_set_and_get():
    appconfig.set_config("credit.accept", 99)
    assert appconfig.get_config("credit.accept", 30) == 99


def test_get_credit_reads_db():
    """get_credit：库值优先于 settings 默认。"""
    appconfig.set_config("credit.daily_login", 7)
    assert appconfig.get_credit("daily_login") == 7
    # 未写入的键回退 settings
    assert appconfig.get_credit("register") == 50


def test_unknown_credit_key():
    import pytest

    with pytest.raises(KeyError):
        appconfig.get_credit("nope")
