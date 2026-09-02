"""S1 测试：全量建表 + 关键约束 + seed + 敏感词 + app_config。"""

import pytest
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError

from app.core.database import SessionLocal, engine
from app.models import CreditAccount, Tag, User


EXPECTED_TABLES = {
    "user",
    "credit_account",
    "credit_log",
    "tag",
    "post",
    "post_tag",
    "answer",
    "comment",
    "like_record",
    "favorite",
    "knowledge_item",
    "gratitude_stat",
    "rank_snapshot",
    "notification",
    "report",
    "admin_action_log",
    "tracking_event",
    "app_config",
}


def test_all_tables_created():
    """20 张表全部建立（18 张业务表 + SQLite 无需单独建 alembic_version 之外无遗漏）。"""
    names = set(inspect(engine).get_table_names())
    assert EXPECTED_TABLES <= names, f"缺失表: {EXPECTED_TABLES - names}"


def test_like_record_composite_pk():
    """like_record 联合主键存在（点赞幂等的结构性保证）。"""
    from app.models import LikeRecord

    cols = {c.name for c in inspect(LikeRecord).primary_key}
    assert cols == {"user_id", "target_type", "target_id"}


def test_credit_balance_nonnegative():
    """credit_account CHECK 约束：balance < 0 触发 IntegrityError。"""
    with SessionLocal() as db:
        u = User(phone="13800000001", password_hash="x", nickname="t")
        db.add(u)
        db.flush()
        db.add(CreditAccount(user_id=u.id, balance=100))
        db.commit()
        with pytest.raises(IntegrityError):
            db.execute(
                CreditAccount.__table__.insert().values(user_id=u.id + 999, balance=-1)
            )
            db.commit()
        db.rollback()


def test_report_dedup_unique():
    """report 唯一键 (reporter_id, target_type, target_id)：重复插入报错。"""
    from app.models import Report

    with SessionLocal() as db:
        db.add(
            Report(
                reporter_id=1, target_type=1, target_id=100, reason=1
            )
        )
        db.commit()
        with pytest.raises(IntegrityError):
            db.add(
                Report(
                    reporter_id=1, target_type=1, target_id=100, reason=2
                )
            )
            db.commit()
        db.rollback()


def test_seed_tags():
    """seed 脚本：12 标签入库且幂等（重复执行不报错不重复）。"""
    from scripts.seed import run

    run()
    with SessionLocal() as db:
        names = [n for (n,) in db.execute(select(Tag.name))]
    assert set(names) >= {
        "计算机", "数学", "物理学", "化学", "生物学", "经济学",
        "法学", "外语", "文学", "医学", "工学", "考研",
    }
    run()  # 幂等
    with SessionLocal() as db:
        count = len(db.execute(select(Tag)).scalars().all())
    assert count == 12


def test_user_theme_config_nullable():
    """user.theme_config：P0 恒 NULL（个性化接口预留字段可写可空）。"""
    with SessionLocal() as db:
        u = User(phone="13800000002", password_hash="x", nickname="t2")
        db.add(u)
        db.commit()
        assert u.theme_config is None
