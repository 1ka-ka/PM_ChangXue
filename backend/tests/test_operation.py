"""V1.13 测试：系统账号自动运营（账号池 / LLM 动作 / 配额 / 降级 / 权限 / 排行等同）。

号段隔离：135 前缀（全部 138 前缀号段已被其他测试文件占用）。
运营账号自身手机号 138000001xx（数字段 101-112，无冲突）。
LLM 相关动作用 monkeypatch 假网关（测试环境 LLM_ENABLED=false）。
"""

import pytest
from sqlalchemy import select

from app.core.database import SessionLocal
from app.gateway.client import gateway as gateway_singleton
from app.models import Answer, GratitudeStat, OperationLog, Post, Tag, User
from app.modules.operation import service as op_service
from scripts.seed import run as seed_tags

_seq = iter(range(1_000_000, 2_000_000))  # 135 前缀独占段


def _user(client, nickname="用户") -> dict:
    r = client.post(
        "/api/auth/register",
        json={"phone": f"135{next(_seq):08d}", "password": "password123", "nickname": nickname},
    )
    return {"Authorization": f"Bearer {r.json()['data']['token']}"}


def _admin(client) -> dict:
    h = _user(client, "运营管理员")
    uid = client.get("/api/auth/me", headers=h).json()["data"]["id"]
    with SessionLocal() as db:
        db.get(User, uid).role = 1
        db.commit()
    return h


def _tags() -> list[int]:
    seed_tags()
    with SessionLocal() as db:
        return [t.id for t in db.execute(select(Tag).order_by(Tag.id)).scalars().all()[:3]]


class FakeGateway:
    """假 LLM：按场景返回合格契约输出（含 quality/summary/reliability 联动场景）。"""

    def invoke(self, scene: str, payload: dict) -> dict:
        if scene == "op_question":
            return {"title": "课程设计选 Django 还是 FastAPI？",
                    "content": "下学期有门课要交一个前后端分离的小项目，" * 4, "tags": ["计算机"]}
        if scene == "op_answer":
            return {"content": "课程设计赶时间选熟悉的框架最重要。" * 8}
        if scene == "op_comment":
            return {"content": "讲得挺清楚的，学到了，感谢分享。"}
        if scene == "quality":
            return {"is_low_quality": False, "reason": ""}
        if scene == "summary":
            return {"summary": "课程设计框架选型问题", "need_review": False}
        if scene == "reliability":
            return {"score": 82, "level": "高"}
        raise AssertionError(f"未知场景: {scene}")


@pytest.fixture()
def fake_llm(monkeypatch):
    monkeypatch.setattr(gateway_singleton, "invoke", FakeGateway().invoke)


def test_status_and_account_pool(client):
    """状态接口：12 个运营账号建档（is_op=1、注册积分）、当日进度为 0。"""
    h = _admin(client)
    r = client.get("/api/admin/operation/status", headers=h)
    data = r.json()["data"]
    assert len(data["accounts"]) == 12
    assert data["quota"] == {"questions": 3, "interactions": 10}
    assert data["today"]["questions"] == 0
    with SessionLocal() as db:
        op_users = db.execute(select(User).where(User.is_op == 1)).scalars().all()
        assert len(op_users) == 12
        u = db.execute(select(User).where(User.phone == "13800000101")).scalar_one()
        assert u.nickname == "码农阿伟"  # 复用 seed_demo 演示账号
    # 普通用户无权访问
    r = client.get("/api/admin/operation/status", headers=_user(client))
    assert r.json()["code"] == 40302


def test_act_question_creates_real_post(client, fake_llm):
    """提问动作：LLM 生成 → 真实落库（作者 is_op、标签、动作日志、AI 摘要）。"""
    _tags()
    with SessionLocal() as db:
        accounts = op_service.ensure_accounts(db)
        result = op_service._act_question(db, accounts)
    assert result["ok"] is True
    with SessionLocal() as db:
        from app.models import PostTag

        post = db.get(Post, result["post_id"])
        assert post is not None
        assert db.get(User, post.author_id).is_op == 1
        assert post.title == "课程设计选 Django 还是 FastAPI？"
        tag_count = len(db.execute(select(PostTag).where(
            PostTag.post_id == post.id)).scalars().all())
        assert 1 <= tag_count <= 3
        log = db.execute(select(OperationLog).where(
            OperationLog.action == op_service.ACT_QUESTION, OperationLog.ok == 1
        ).order_by(OperationLog.id.desc())).scalars().first()
        assert log is not None and log.user_id == post.author_id
        assert post.ai_summary is not None  # 同步补了 AI 摘要


def test_act_answer_and_comment(client, fake_llm):
    """回答/评论/回复动作：多轮随机执行后运营账号至少产出一个回答。"""
    tags = _tags()
    h = _user(client, "路人甲")
    client.post("/api/posts", headers=h, json={
        "title": "Python 装饰器执行顺序怎么理解？",
        "content": "多层装饰器从下往上装饰、从上往下执行，总是记不住。", "tag_ids": tags[:1],
    })
    with SessionLocal() as db:
        accounts = op_service.ensure_accounts(db)
        for _ in range(12):
            op_service._act_answer(db, accounts)
        for _ in range(8):
            op_service._act_comment(db, accounts)
        for _ in range(8):
            op_service._act_reply(db, accounts)
        op_answers = db.execute(select(Answer).join(
            User, User.id == Answer.author_id
        ).where(User.is_op == 1)).scalars().all()
        assert len(op_answers) >= 1  # 运营账号至少答了一帖


def test_op_account_joins_rank_on_accept(client, fake_llm):
    """地位等同：运营账号的回答被采纳 → 感谢值入榜（与真人同一链路）。"""
    tags = _tags()
    h = _user(client, "提问真人")
    pid = client.post("/api/posts", headers=h, json={
        "title": "TCP 滑动窗口和拥塞控制是一回事吗？",
        "content": "复习网络时把这两个概念搞混了。", "tag_ids": tags[:1],
    }).json()["data"]["id"]
    with SessionLocal() as db:
        accounts = op_service.ensure_accounts(db)
        op_user = accounts[0]
        aid = op_service.answer_service.create_answer(
            db, op_user, pid, "滑动窗口管接收方流量控制，拥塞控制管网络承载能力，两者作用层不同。" * 3
        )["id"]
    r = client.post(f"/api/answers/{aid}/accept", headers=h)
    assert r.json()["code"] == 0
    with SessionLocal() as db:
        rows = db.execute(select(GratitudeStat).where(
            GratitudeStat.user_id == op_user.id, GratitudeStat.period_type == 3
        )).scalars().all()
        assert sum(x.value for x in rows) >= 30  # 入榜（累计周期 +30）


def test_quota_gate(client):
    """配额闸门：当日配额写满 + LLM 不可用 → 调度动作空转（手动触发不受限）。"""
    with SessionLocal() as db:
        accounts = op_service.ensure_accounts(db)
        db.add_all([OperationLog(action=op_service.ACT_QUESTION, ok=1) for _ in range(3)])
        db.add_all([OperationLog(action=a, ok=1) for _ in range(2)
                    for a in op_service._INTERACTION_ACTIONS])
        db.commit()
        result = op_service._do_one_action(db, accounts, manual=False)
        assert result["action"] == 0 and "配额" in result["detail"]


def test_manual_run_degraded_without_llm(client):
    """降级：LLM 关闭时手动触发仍可用（仅免 LLM 动作或跳过），接口不报错。"""
    h = _admin(client)
    r = client.post("/api/admin/operation/run", headers=h)
    body = r.json()
    assert body["code"] == 0
    for item in body["data"]["executed"]:
        assert "action" in item and "ok" in item  # 每个动作均有结构化结果
    # 普通用户无权触发
    r = client.post("/api/admin/operation/run", headers=_user(client))
    assert r.json()["code"] == 40302


def test_subsidy_on_low_balance(client):
    """积分补贴：余额低于阈值的运营账号补到目标值（TASK 流水，不受日封顶）。"""
    with SessionLocal() as db:
        accounts = op_service.ensure_accounts(db)
        poor = accounts[-1]
        from app.modules.credit import service as credit_service
        from app.models import CreditAccount
        account = db.execute(select(CreditAccount).where(
            CreditAccount.user_id == poor.id)).scalar_one()
        account.balance = 10
        db.commit()
        granted = op_service._subsidize(db, accounts)
        assert any(g["user_id"] == poor.id for g in granted)
        assert credit_service.get_balance(db, poor.id) == 300  # 补到目标值（注资不受日封顶）
