"""S3 测试：积分账务核心（TC-credit 全组，账务地基，必须 100% 通过）。"""

from datetime import datetime, timedelta

from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.exceptions import BizError
from app.models import CreditAccount, CreditLog, User
from app.modules.credit import service
from app.modules.credit.sources import CreditSource

_seq = iter(range(2_000_000, 3_000_000))


def _make_user(nickname="测试用户") -> int:
    with SessionLocal() as db:
        u = User(phone=f"138{next(_seq):08d}", password_hash="x", nickname=nickname)
        db.add(u)
        db.commit()
        return u.id


def _balance(user_id: int) -> int:
    with SessionLocal() as db:
        a = db.get(CreditAccount, user_id)
        return a.balance if a else 0


def _logs(user_id: int) -> list[CreditLog]:
    with SessionLocal() as db:
        return (
            db.execute(
                select(CreditLog)
                .where(CreditLog.user_id == user_id)
                .order_by(CreditLog.id)
            )
            .scalars()
            .all()
        )


def test_register_grant():
    """注册 50：发放+流水 balance_after 连续。"""
    uid = _make_user()
    with SessionLocal() as db:
        granted = service.grant(db, uid, CreditSource.REGISTER, 50, note="注册开户赠送")
        db.commit()
    assert granted == 50
    assert _balance(uid) == 50
    logs = _logs(uid)
    assert len(logs) == 1
    assert logs[0].change == 50 and logs[0].balance_after == 50


def test_daily_login_grant_and_idempotent():
    """登录 5 + 当日重复领取幂等。"""
    uid = _make_user()
    with SessionLocal() as db:
        granted = service.grant(db, uid, CreditSource.DAILY_LOGIN, 5, note="每日登录")
        db.commit()
    assert granted == 5
    with SessionLocal() as db:
        assert service.has_daily_login_today(db, uid) is True
    # 第二次调用由 router 层幂等拦截；service 层直发会再记流水（封顶内）——验证 router 层语义见 API 测试


def test_daily_cap_blocks_and_partial():
    """日封顶 100：超限记 0 分流水不发放；部分超额只发剩余额度。"""
    uid = _make_user()
    with SessionLocal() as db:
        # 先发 95（模拟多来源产出）
        service.grant(db, uid, CreditSource.TASK, 95, note="任务")
        db.commit()
    with SessionLocal() as db:
        # 采纳 +30，仅剩 5 额度 → 只发 5
        granted = service.grant(db, uid, CreditSource.ACCEPTED, 30, note="采纳")
        db.commit()
    assert granted == 5
    assert _balance(uid) == 100
    logs = _logs(uid)
    assert logs[-1].change == 5

    with SessionLocal() as db:
        # 再来一次：0 额度 → 发放 0，流水记 0 且 note 标封顶
        granted = service.grant(db, uid, CreditSource.ACCEPTED, 30, note="采纳2")
        db.commit()
    assert granted == 0
    assert _balance(uid) == 100
    logs = _logs(uid)
    assert logs[-1].change == 0 and "封顶" in logs[-1].note


def test_deduct_ok_and_insufficient():
    """扣减成功+流水；余额不足抛 40902 且无流水。"""
    uid = _make_user()
    with SessionLocal() as db:
        service.grant(db, uid, CreditSource.REGISTER, 50, note="注册")
        db.commit()
    with SessionLocal() as db:
        service.deduct(db, uid, CreditSource.REWARD, 30, note="悬赏")
        db.commit()
    assert _balance(uid) == 20

    with SessionLocal() as db:
        before = len(_logs(uid))
        try:
            service.deduct(db, uid, CreditSource.REWARD, 50, note="悬赏2")
            raise AssertionError("应抛 40902")
        except BizError as e:
            assert e.code == 40902
            assert "20" in e.msg  # 含余额
        db.rollback()
    assert len(_logs(uid)) == before  # 无新流水
    assert _balance(uid) == 20


def test_ledger_continuity():
    """流水 balance_after 连续性：多笔操作后逐条校验。"""
    uid = _make_user()
    with SessionLocal() as db:
        service.grant(db, uid, CreditSource.REGISTER, 50, note="注册")
        service.deduct(db, uid, CreditSource.REWARD, 20, note="悬赏")
        service.grant(db, uid, CreditSource.ACCEPTED, 30, note="采纳")
        db.commit()
    logs = _logs(uid)
    running = 0
    for log in logs:
        running += log.change
        assert log.balance_after == running


def test_recall_over_balance_clamps_to_zero():
    """追回超余额：追回至 0，流水记实际值（40912 语义）。"""
    uid = _make_user()
    with SessionLocal() as db:
        service.grant(db, uid, CreditSource.REGISTER, 50, note="注册")
        db.commit()
    with SessionLocal() as db:
        actual = service.recall(db, uid, 80, note="低质量追回")
        db.commit()
    assert actual == 50
    assert _balance(uid) == 0
    logs = _logs(uid)
    assert logs[-1].change == -50 and "实际追回" in logs[-1].note


def test_grant_creates_missing_account():
    """账户不存在时懒创建。"""
    uid = _make_user("无账户用户")
    with SessionLocal() as db:
        granted = service.grant(db, uid, CreditSource.ACCEPTED, 30, note="采纳")
        db.commit()
    assert granted == 30 and _balance(uid) == 30


# ---- API 层测试 ----


def _auth_header(client) -> dict:
    r = client.post(
        "/api/auth/register",
        json={"phone": f"139{next(_seq):08d}", "password": "password123", "nickname": "api用户"},
    )
    return {"Authorization": f"Bearer {r.json()['data']['token']}"}


def test_api_daily_login_and_idempotent(client):
    """API：每日登录 5 分；重复调用返回 granted=0。"""
    h = _auth_header(client)
    r = client.post("/api/credit/daily-login", headers=h)
    assert r.json()["data"]["granted"] == 5
    r = client.post("/api/credit/daily-login", headers=h)
    assert r.json()["data"] == {"granted": 0, "reason": "今日已领取"}


def test_api_balance_and_logs(client):
    """API：余额=注册50+登录5；明细含 source_text 倒序。"""
    h = _auth_header(client)
    client.post("/api/credit/daily-login", headers=h)
    r = client.get("/api/credit/balance", headers=h)
    assert r.json()["data"]["balance"] == 55

    r = client.get("/api/credit/logs", headers=h)
    data = r.json()["data"]
    assert data["total"] == 2
    items = data["items"]
    assert items[0]["source_text"] == "每日登录"  # 倒序最新在前
    assert items[1]["source_text"] == "注册赠送"
    assert items[1]["change"] == 50
