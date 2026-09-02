"""V1.3 测试：AI 四场景接入（ref_answer / reliability / quality / moderation，全部 mock）。"""

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import Post, Report, Tag
from app.modules.moderation import service as mod_service
from app.modules.post import answers as answers_service
from app.modules.post import service as post_service
from scripts.seed import run as seed_tags

_seq = iter(range(7_000_000, 8_000_000))


def _user(client, nickname) -> dict:
    r = client.post(
        "/api/auth/register",
        json={"phone": f"135{next(_seq):08d}", "password": "password123", "nickname": nickname},
    )
    return {"Authorization": f"Bearer {r.json()['data']['token']}"}


def _tag_id() -> int:
    seed_tags()
    with SessionLocal() as db:
        return db.execute(select(Tag.id).order_by(Tag.id)).scalars().first()


def _post(client, h, title="怎么理解操作系统的死锁", content="四个必要条件分别是什么？怎么打破？"):
    tid = _tag_id()
    r = client.post(
        "/api/posts", json={"title": title, "content": content, "tag_ids": [tid]}, headers=h
    )
    assert r.json()["code"] == 0, r.json()
    return r.json()["data"]["id"]


# ---- ref_answer 参考回答 ----


def test_ai_answer_generate_and_cache(client, monkeypatch):
    """触发生成：落库缓存；二次触发命中缓存不重复调用；详情页可读。"""
    h = _user(client, "提问者")
    pid = _post(client, h)

    calls = []

    def fake_invoke(scene, payload):
        calls.append(scene)
        return {"answer_text": "死锁四条件：互斥/持有等待/不可剥夺/循环等待；打破任一即可。", "confidence": 0.9}

    monkeypatch.setattr("app.gateway.client.gateway.invoke", fake_invoke)
    r = client.post(f"/api/posts/{pid}/ai-answer", headers=h)
    data = r.json()["data"]
    assert data["cached"] is False
    assert "死锁" in data["ai_answer"]

    r2 = client.post(f"/api/posts/{pid}/ai-answer", headers=h)  # 二次触发
    assert r2.json()["data"]["cached"] is True
    assert calls == ["ref_answer"]  # 只真实调用一次

    detail = client.get(f"/api/posts/{pid}").json()["data"]
    assert "死锁" in detail["ai_answer"]


def test_ai_answer_degraded_returns_error(client):
    """LLM 关闭（测试环境恒关）：返回 40001 提示暂不可用，不落库。"""
    h = _user(client, "提问者")
    pid = _post(client, h)
    r = client.post(f"/api/posts/{pid}/ai-answer", headers=h)
    assert r.json()["code"] == 40001
    with SessionLocal() as db:
        assert db.get(Post, pid).ai_answer is None


def test_ai_answer_edit_invalidates_cache(client, monkeypatch):
    """编辑帖子 → AI 参考回答缓存作废，可重新生成。"""
    h = _user(client, "提问者")
    pid = _post(client, h)
    monkeypatch.setattr(
        "app.gateway.client.gateway.invoke",
        lambda s, p: {"answer_text": "旧回答", "confidence": 0.9},
    )
    client.post(f"/api/posts/{pid}/ai-answer", headers=h)

    r = client.put(f"/api/posts/{pid}", json={"title": "怎么理解操作系统的死锁", "content": "内容更新了", "tag_ids": [_tag_id()]}, headers=h)
    assert r.json()["code"] == 0
    with SessionLocal() as db:
        assert db.get(Post, pid).ai_answer is None  # 缓存已清


# ---- reliability 可靠性评分 ----


def test_reliability_task_mock_success(client, monkeypatch):
    """回答提交后异步评分：字段落库，序列化带出。"""
    h = _user(client, "提问者")
    pid = _post(client, h)
    h2 = _user(client, "回答者")
    monkeypatch.setattr(
        "app.gateway.client.gateway.invoke",
        lambda s, p: {"score": 85, "level": "高"},
    )
    r = client.post(f"/api/posts/{pid}/answers", json={"content": "互斥、持有等待、不可剥夺、循环等待是死锁四条件。"}, headers=h2)
    aid = r.json()["data"]["id"]

    answers_service.generate_reliability_task(aid)
    detail = client.get(f"/api/posts/{pid}").json()["data"]
    target = next(a for a in detail["answers"] if a["id"] == aid)
    assert target["ai_rel_score"] == 85
    assert target["ai_rel_level"] == "高"


def test_reliability_task_degraded_silent(client):
    """LLM 关闭：任务静默，字段保持 None（前端不渲染徽标）。"""
    h = _user(client, "提问者")
    pid = _post(client, h)
    h2 = _user(client, "回答者")
    r = client.post(f"/api/posts/{pid}/answers", json={"content": "正常回答内容，讲解死锁的必要条件。"}, headers=h2)
    aid = r.json()["data"]["id"]

    answers_service.generate_reliability_task(aid)  # 测试环境 LLM 关 → 降级
    detail = client.get(f"/api/posts/{pid}").json()["data"]
    target = next(a for a in detail["answers"] if a["id"] == aid)
    assert target["ai_rel_score"] is None
    assert target["ai_rel_level"] is None


# ---- quality 质量检测 ----


def test_quality_blocks_low_quality_answer(client, monkeypatch):
    """低质回答（灌水）：40913 拦截，不入库。"""
    h = _user(client, "提问者")
    pid = _post(client, h)
    h2 = _user(client, "灌水者")
    monkeypatch.setattr(
        "app.gateway.client.gateway.invoke",
        lambda s, p: {"is_low_quality": True, "reason": "纯表情灌水"},
    )
    r = client.post(f"/api/posts/{pid}/answers", json={"content": "哈哈哈哈哈哈哈哈"}, headers=h2)
    assert r.json()["code"] == 40913
    assert "灌水" in r.json()["msg"]
    detail = client.get(f"/api/posts/{pid}").json()["data"]
    assert detail["answer_count"] == 0  # 未入库


def test_quality_allows_normal_and_degrades(client, monkeypatch):
    """正常回答放行；LLM 降级（关闭）同样放行不阻塞。"""
    h = _user(client, "提问者")
    pid = _post(client, h)
    h2 = _user(client, "回答者")

    def fake_invoke(scene, payload):
        if scene == "quality":
            return {"is_low_quality": False, "reason": ""}
        return {"score": 90, "level": "高"}  # reliability 后台任务

    monkeypatch.setattr("app.gateway.client.gateway.invoke", fake_invoke)
    r = client.post(f"/api/posts/{pid}/answers", json={"content": "死锁需要同时满足四个条件。"}, headers=h2)
    assert r.json()["code"] == 0

    h3 = _user(client, "回答者2")
    r2 = client.post(  # LLM 关闭（conftest 恒关；quality 检测走真实降级放行，reliability 任务内静默）
        f"/api/posts/{pid}/answers", json={"content": "补充：资源分配图可检测循环等待。"}, headers=h3
    )
    assert r2.json()["code"] == 0


# ---- moderation 违规分级 ----


def test_moderation_task_mock_success(client, monkeypatch):
    """举报后异步分级：ai_level 落库，管理列表带出。"""
    h = _user(client, "提问者")
    pid = _post(client, h)
    h2 = _user(client, "举报者")
    monkeypatch.setattr(
        "app.gateway.client.gateway.invoke",
        lambda s, p: {"level": "高", "violation_type": "垃圾广告"},
    )
    r = client.post(
        "/api/reports",
        json={"target_type": 1, "target_id": pid, "reason": 1, "detail": "疑似广告"},
        headers=h2,
    )
    assert r.json()["code"] == 0

    with SessionLocal() as db:
        rid = db.execute(select(Report.id).where(Report.target_id == pid)).scalar()
    mod_service.moderate_report_task(rid)
    with SessionLocal() as db:
        assert db.get(Report, rid).ai_level == "高"

    # 管理员视角列表带出（提升管理员后再查：role=1）
    with SessionLocal() as db:
        from app.models import User

        u = db.get(User, _uid_of(h2))
        u.role = 1
        db.commit()
    r = client.get("/api/admin/reports", headers=h2)
    item = next(i for i in r.json()["data"]["items"] if i["target_id"] == pid)
    assert item["ai_level"] == "高"
    assert item["ai_violation_type"] == "垃圾广告"


def _uid_of(h: dict) -> int:
    import jwt

    from app.core.config import settings

    token = h["Authorization"].split(" ")[1]
    return int(jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])["uid"])


def test_moderation_task_degraded_and_deleted_target(client):
    """LLM 关闭静默；目标已软删跳过。"""
    h = _user(client, "提问者")
    pid = _post(client, h)
    h2 = _user(client, "举报者")
    r = client.post("/api/reports", json={"target_type": 1, "target_id": pid, "reason": 5}, headers=h2)
    assert r.json()["code"] == 0
    with SessionLocal() as db:
        rid = db.execute(select(Report.id).where(Report.target_id == pid)).scalar()
    mod_service.moderate_report_task(rid)  # LLM 关 → 静默
    with SessionLocal() as db:
        assert db.get(Report, rid).ai_level is None

    # 软删后再跑任务（目标不存在路径）
    client.delete(f"/api/posts/{pid}", headers=h)
    mod_service.moderate_report_task(rid)  # 不应抛异常
