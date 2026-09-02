"""V1.5 测试：AI 无人值守兜底（run_ai_fallback 直调 + gateway mock）。"""

from datetime import datetime, timedelta

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import Post, Tag
from scripts.seed import run as seed_tags

_seq = iter(range(9_000_000, 9_500_000))


def _user(client, nickname) -> dict:
    r = client.post(
        "/api/auth/register",
        json={"phone": f"135{next(_seq):08d}", "password": "password123", "nickname": nickname},
    )
    return {"Authorization": f"Bearer {r.json()['data']['token']}"}


def _post(client, h, title="无人回答的帖子", content="这道题怎么做？") -> int:
    seed_tags()
    with SessionLocal() as db:
        tid = db.execute(select(Tag.id).order_by(Tag.id)).scalars().first()
    r = client.post(
        "/api/posts", json={"title": title, "content": content, "tag_ids": [tid]}, headers=h
    )
    assert r.json()["code"] == 0, r.json()
    return r.json()["data"]["id"]


def _age_post(pid: int, minutes: int) -> None:
    """把帖子 created_at 拨到 minutes 分钟前（模拟超时无人回答）。"""
    with SessionLocal() as db:
        post = db.get(Post, pid)
        post.created_at = datetime.now() - timedelta(minutes=minutes)
        db.commit()


def _ai_answer_of(pid: int) -> str | None:
    with SessionLocal() as db:
        return db.get(Post, pid).ai_answer


def _mock_invoke(monkeypatch, text="AI 兜底回答：思路分三步。", fail=False):
    """打开 LLM 开关（conftest 恒关）+ mock gateway.invoke（零真实调用）。"""
    from app.core.config import settings
    from app.gateway.client import LLMDegradedError, gateway

    monkeypatch.setattr(settings, "LLM_ENABLED", True)
    calls = []

    def fake(scene, payload):
        calls.append((scene, payload["post_id"]))
        if fail:
            raise LLMDegradedError("mock 降级")
        return {"answer_text": text, "confidence": 0.85}

    monkeypatch.setattr(gateway, "invoke", fake)
    return calls


def test_fallback_generates_for_stale_unanswered(client, monkeypatch):
    """超时无回答帖：兜底生成 ai_answer；新帖不处理。"""
    from app.jobs.ai_fallback import run_ai_fallback

    h = _user(client, "兜底提问者")
    stale_pid, fresh_pid = _post(client, h), _post(client, h)
    _age_post(stale_pid, minutes=40)
    _age_post(fresh_pid, minutes=5)

    calls = _mock_invoke(monkeypatch)
    run_ai_fallback()
    assert calls == [("ref_answer", stale_pid)]  # 只处理超时帖
    assert _ai_answer_of(stale_pid) == "AI 兜底回答：思路分三步。"
    assert _ai_answer_of(fresh_pid) is None


def test_fallback_skips_answered_and_generated(client, monkeypatch):
    """已有人回答的帖 / 已生成过的帖：跳过。"""
    from app.jobs.ai_fallback import run_ai_fallback

    h1, h2 = _user(client, "提问者A"), _user(client, "回答者B")
    answered_pid, done_pid = _post(client, h1), _post(client, h1)
    _age_post(answered_pid, minutes=40)
    _age_post(done_pid, minutes=40)

    r = client.post(
        f"/api/posts/{answered_pid}/answers", json={"content": "人来回答了"}, headers=h2
    )
    assert r.json()["code"] == 0, r.json()
    with SessionLocal() as db:  # 已生成过（模拟用户手动触发过）
        db.get(Post, done_pid).ai_answer = "已有 AI 回答"
        db.commit()

    calls = _mock_invoke(monkeypatch)
    run_ai_fallback()
    assert calls == []


def test_fallback_degrades_silently(client, monkeypatch):
    """LLM 降级：不抛异常，ai_answer 保持 None（下轮重试）。"""
    from app.jobs.ai_fallback import run_ai_fallback

    h = _user(client, "降级提问者")
    pid = _post(client, h)
    _age_post(pid, minutes=40)
    _mock_invoke(monkeypatch, fail=True)
    run_ai_fallback()  # 不应抛异常
    assert _ai_answer_of(pid) is None


def test_fallback_batch_limit(client, monkeypatch):
    """批量上限：超时帖多于 AI_FALLBACK_BATCH 时每轮只处理前 BATCH 条。"""
    from app.core.config import settings
    from app.jobs.ai_fallback import run_ai_fallback

    monkeypatch.setattr(settings, "AI_FALLBACK_BATCH", 2)
    h = _user(client, "批量提问者")
    pids = [_post(client, h) for _ in range(3)]
    for i, pid in enumerate(pids):
        _age_post(pid, minutes=40 + i)  # 越老越先处理

    calls = _mock_invoke(monkeypatch)
    run_ai_fallback()
    assert len(calls) == 2
    assert [p for _, p in calls] == [pids[2], pids[1]]  # 最老优先（created_at 升序：42 分 > 41 分）


def test_fallback_disabled_when_llm_off(client, monkeypatch):
    """LLM 关闭：任务直接空转（gateway 不被调用；勿用 _mock_invoke，其会打开开关）。"""
    from app.core.config import settings
    from app.gateway.client import gateway
    from app.jobs.ai_fallback import run_ai_fallback

    calls = []
    monkeypatch.setattr(gateway, "invoke", lambda scene, payload: calls.append(scene))
    monkeypatch.setattr(settings, "LLM_ENABLED", False)
    run_ai_fallback()
    assert calls == []
