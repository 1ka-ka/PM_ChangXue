"""V1.2 测试：LLM 网关客户端 + AI 摘要生成（全部 mock，零真实调用）。"""

from sqlalchemy import select

from app.core.database import SessionLocal
from app.gateway.client import LLMDegradedError, _extract_json, gateway
from app.models import Post, Tag
from app.modules.post import service as post_service
from scripts.seed import run as seed_tags

_seq = iter(range(6_000_000, 7_000_000))


def _user(client, nickname) -> dict:
    r = client.post(
        "/api/auth/register",
        json={"phone": f"136{next(_seq):08d}", "password": "password123", "nickname": nickname},
    )
    return {"Authorization": f"Bearer {r.json()['data']['token']}"}


def _create_post(client, h, title="考研数学极限怎么求", content="洛必达法则和等价无穷小怎么选？"):
    seed_tags()
    with SessionLocal() as db:
        tag_id = db.execute(select(Tag.id).order_by(Tag.id)).scalars().first()
    r = client.post(
        "/api/posts",
        json={"title": title, "content": content, "tag_ids": [tag_id]},
        headers=h,
    )
    assert r.json()["code"] == 0, r.json()
    return r.json()["data"]["id"]


# ---- 网关客户端 ----


def test_invoke_degraded_when_disabled():
    """LLM_ENABLED=False：任何场景直接降级异常，不发网络请求。"""
    import app.core.config as config

    origin = config.settings.LLM_ENABLED
    config.settings.LLM_ENABLED = False
    try:
        try:
            gateway.invoke("summary", {"title": "测试标题"})
            raise AssertionError("应抛 LLMDegradedError")
        except LLMDegradedError:
            pass
    finally:
        config.settings.LLM_ENABLED = origin


def test_invoke_input_contract_validation():
    """输入不合契约（title 为空）：降级异常而非透传给模型。"""
    import app.core.config as config

    origin, origin_key = config.settings.LLM_ENABLED, config.settings.LLM_API_KEY
    config.settings.LLM_ENABLED, config.settings.LLM_API_KEY = True, "fake-key"
    try:
        try:
            gateway.invoke("summary", {"title": ""})
            raise AssertionError("应抛 LLMDegradedError")
        except LLMDegradedError:
            pass
        try:
            gateway.invoke("unknown_scene", {"title": "x"})
            raise AssertionError("未知场景应抛 LLMDegradedError")
        except LLMDegradedError:
            pass
    finally:
        config.settings.LLM_ENABLED, config.settings.LLM_API_KEY = origin, origin_key


def test_extract_json_variants():
    """模型输出解析：裸 JSON / 代码围栏 / 前后杂文本。"""
    assert _extract_json('{"summary": "ok", "need_review": false}')["summary"] == "ok"
    assert _extract_json('```json\n{"a": 1}\n```')["a"] == 1
    assert _extract_json('好的，结果如下：{"a": {"b": 2}} 以上。')["a"]["b"] == 2
    try:
        _extract_json("没有任何 JSON")
        raise AssertionError("应抛 LLMDegradedError")
    except LLMDegradedError:
        pass


# ---- AI 摘要生成任务 ----


def test_summary_task_mock_success(client, monkeypatch):
    """生成成功：ai_summary 落库，卡片 summary 优先 AI 且 is_ai_summary=True。"""
    h = _user(client, "提问者")
    pid = _create_post(client, h)

    monkeypatch.setattr(
        "app.gateway.client.gateway.invoke",
        lambda scene, payload: {"summary": "AI 摘要：求解函数极限时洛必达与等价无穷小的选择", "need_review": False},
    )
    post_service.generate_ai_summary_task(pid)

    with SessionLocal() as db:
        p = db.get(Post, pid)
        assert p.ai_summary is not None and "AI 摘要" in p.ai_summary

    r = client.get(f"/api/posts/{pid}")
    data = r.json()["data"]
    assert data["is_ai_summary"] is True
    assert "AI 摘要" in data["summary"]
    assert "AI 摘要" in data["ai_summary"]


def test_summary_task_degraded_silent(client):
    """LLM 降级（未启用）：任务静默返回，ai_summary 保持 None，卡片回退正文截断。"""
    h = _user(client, "提问者")
    pid = _create_post(client, h, content="洛必达法则的适用条件是什么")

    post_service.generate_ai_summary_task(pid)  # 测试环境 LLM_ENABLED=false → 降级路径

    with SessionLocal() as db:
        p = db.get(Post, pid)
        assert p.ai_summary is None

    r = client.get(f"/api/posts/{pid}")
    data = r.json()["data"]
    assert data["is_ai_summary"] is False
    assert data["summary"].startswith("洛必达法则")
    assert data["ai_summary"] is None


def test_summary_task_skips_deleted(client, monkeypatch):
    """软删帖不生成摘要（任务直接返回）。"""
    h = _user(client, "提问者")
    pid = _create_post(client, h)
    client.delete(f"/api/posts/{pid}", headers=h)

    called = []
    monkeypatch.setattr(
        "app.gateway.client.gateway.invoke",
        lambda scene, payload: called.append(1) or {"summary": "x", "need_review": False},
    )
    post_service.generate_ai_summary_task(pid)
    assert called == []  # 帖子已软删，未调用 LLM

    with SessionLocal() as db:
        assert db.get(Post, pid).ai_summary is None


def test_create_post_with_llm_disabled_no_crash(client):
    """发帖接口在 LLM 关闭时正常返回（后台任务降级不阻塞响应）。"""
    h = _user(client, "提问者")
    pid = _create_post(client, h, title="线性代数特征值怎么求")
    assert pid > 0
