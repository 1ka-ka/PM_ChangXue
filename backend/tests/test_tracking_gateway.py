"""S10 测试：埋点批量上报 TC-tracking + LLM 网关契约 TC-gateway + P0 零调用断言。"""

from sqlalchemy import select

from app.core.config import settings
from app.core.database import SessionLocal
from app.gateway.contracts import (
    SCENE_CONTRACTS,
    ModerationInput,
    ModerationOutput,
    QualityInput,
    QualityOutput,
    RefAnswerInput,
    RefAnswerOutput,
    ReliabilityInput,
    ReliabilityOutput,
    SummaryInput,
    SummaryOutput,
)
from app.models import TrackingEvent

_seq = iter(range(9_000_000, 9_500_000))


def _user(client, nickname) -> dict:
    r = client.post(
        "/api/auth/register",
        json={"phone": f"138{next(_seq):08d}", "password": "password123", "nickname": nickname},
    )
    return {"Authorization": f"Bearer {r.json()['data']['token']}"}


# ---------- TC-tracking ----------


def test_events_batch_persist_and_204(client):
    """批量上报：204 空响应 + 落库（匿名与登录态均可用）。"""
    r = client.post(
        "/api/events/batch",
        json={"events": [{"name": "page_view", "props": {"path": "/feed"}}]},
    )
    assert r.status_code == 204 and r.content == b""

    h = _user(client, "埋点用户")
    uid = client.get("/api/auth/me", headers=h).json()["data"]["id"]
    r = client.post(
        "/api/events/batch",
        json={
            "events": [
                {"name": "post_create", "props": {"post_id": 1}},
                {"name": "search_use", "props": None},
            ]
        },
        headers=h,
    )
    assert r.status_code == 204

    with SessionLocal() as db:
        rows = (
            db.execute(
                select(TrackingEvent)
                .where(TrackingEvent.event_name.in_(["page_view", "post_create", "search_use"]))
                .order_by(TrackingEvent.id)
            )
            .scalars()
            .all()
        )
    by_name = {e.event_name: e for e in rows}
    assert by_name["page_view"].user_id is None  # 匿名
    assert by_name["post_create"].user_id == uid  # 登录态关联
    assert by_name["search_use"].props is None


def test_events_batch_validation(client):
    """批次校验：空列表/超 20 条 → 全局校验处理器转 200+40001（§2.1 约定）。"""
    r = client.post("/api/events/batch", json={"events": []}).json()
    assert r["code"] == 40001
    r = client.post(
        "/api/events/batch",
        json={"events": [{"name": f"e{i}"} for i in range(21)]},
    ).json()
    assert r["code"] == 40001


def test_events_batch_rate_limit_429(client):
    """令牌桶限流：61 次/分触发 40006 + HTTP 429。"""
    from app.modules.tracking import service as tracking_service

    tracking_service.limiter._buckets.clear()  # 隔离：清空其他用例残留桶
    body = {"events": [{"name": "limit_probe"}]}
    statuses = []
    for _ in range(61):
        r = client.post("/api/events/batch", json=body)
        statuses.append((r.status_code, r.json().get("code") if r.status_code != 204 else 0))
    # 前 60 次成功（可能含此前用例消耗，断言仅验证第 61 次后被拦）
    assert any(s == 429 for s, _ in statuses)
    four29 = [c for s, c in statuses if s == 429]
    assert all(c == 40006 for c in four29)


# ---------- TC-gateway：五契约 round-trip ----------


def test_contract_round_trips():
    """五契约 round-trip：构造 → dump → load → 语义等价；校验约束生效。"""
    cases = [
        (
            SummaryInput(title="标题", content="正文", images_text=["图1 OCR"]),
            SummaryOutput(summary="这是一段摘要", need_review=False),
        ),
        (
            RefAnswerInput(post_id=1, title="标题", content="正文", tag_names=["计算机"]),
            RefAnswerOutput(answer_text="参考回答", confidence=0.87),
        ),
        (
            ReliabilityInput(post_id=1, post_title="标题", post_content="正文", answer_text="回答"),
            ReliabilityOutput(score=85, level="高"),
        ),
        (
            QualityInput(answer_text="回答", author_history=["历史回答1"]),
            QualityOutput(is_low_quality=True, reason="灌水"),
        ),
        (
            ModerationInput(content="待审内容"),
            ModerationOutput(level="高", violation_type="人身攻击"),
        ),
    ]
    for inp, out in cases:
        assert type(inp).model_validate(inp.model_dump()) == inp
        assert type(out).model_validate(out.model_dump()) == out
        # JSON round-trip（网关传输形态）
        import json

        assert type(out).model_validate_json(json.dumps(out.model_dump(mode="json"))) == out


def test_contract_field_constraints():
    """字段约束：summary ≤100 字、score 0-100、confidence 0-1、level 枚举。"""
    import pydantic

    with_ = pydantic.ValidationError
    try:
        SummaryOutput(summary="超" * 101, need_review=False)
        raise AssertionError("summary 超 100 字未被拦截")
    except with_:
        pass
    try:
        ReliabilityOutput(score=101, level="高")
        raise AssertionError("score 超 100 未被拦截")
    except with_:
        pass
    try:
        RefAnswerOutput(answer_text="x", confidence=1.5)
        raise AssertionError("confidence 超 1 未被拦截")
    except with_:
        pass
    try:
        ModerationOutput(level="不存在的级别")
        raise AssertionError("level 枚举未被拦截")
    except with_:
        pass


def test_scene_map_and_contracts_registry():
    """场景注册表：五场景齐全，输入/输出模型与 ARCH §6 对应。"""
    assert set(SCENE_CONTRACTS) == {"summary", "ref_answer", "reliability", "quality", "moderation"}
    assert SCENE_CONTRACTS["summary"] == (SummaryInput, SummaryOutput)
    assert SCENE_CONTRACTS["moderation"] == (ModerationInput, ModerationOutput)


def test_p0_zero_llm_call_path():
    """P0 零模型调用：LLM_ENABLED=False；gateway 目录无 client/HTTP 调用代码。"""
    assert settings.LLM_ENABLED is False
    import inspect
    from pathlib import Path

    import app.gateway as gw

    gw_dir = Path(inspect.getfile(gw)).parent
    py_files = list(gw_dir.rglob("*.py"))
    assert py_files, "gateway 目录存在"
    # client.py（P1 外部调用实现）不存在
    assert not (gw_dir / "client.py").exists()
    # 现有契约文件不包含 http 请求调用代码
    for f in py_files:
        src = f.read_text(encoding="utf-8")
        for kw in ("httpx", "requests.post", "urllib.request", "aiohttp"):
            assert kw not in src, f"{f.name} 不应包含外部调用代码：{kw}"
