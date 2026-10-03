"""V1.19 相似推荐语义升级测试：语义余弦优先于字面 bigram / 查询向量不可用整轮回退
bigram / 发帖后台任务计算向量（LLM 失败静默降级不影响主流程）。"""

import pytest

from app.core.database import SessionLocal
from app.gateway.client import LLMDegradedError, gateway
from app.models import Post

PASSWORD = "password123"
# 独立号段：136 前缀 3M-4M（136 已占用段：mall 1M-2M / llm_gateway 6M-7M / me_center 8M-9M）
_seq = iter(range(3_000_000, 4_000_000))


def _unique_phone() -> str:
    return f"136{next(_seq):08d}"


def _register(client, nickname="用户"):
    r = client.post(
        "/api/auth/register",
        json={"phone": _unique_phone(), "password": PASSWORD, "nickname": nickname},
    )
    body = r.json()
    assert body["code"] == 0, body
    return {"Authorization": f"Bearer {body['data']['token']}"}


def _first_tag_id(client) -> int:
    from sqlalchemy import select

    from app.core.database import SessionLocal
    from app.models import Tag
    from scripts.seed import run as seed_tags

    with SessionLocal() as db:
        tag = db.execute(select(Tag).limit(1)).scalar()
        if tag is not None:
            return tag.id
    seed_tags()  # 共享库首个用例运行时可能尚未 seed
    with SessionLocal() as db:
        return db.execute(select(Tag).limit(1)).scalar_one().id


def _create_post(client, h, title, content="测试正文内容"):
    r = client.post(
        "/api/posts",
        json={"title": title, "content": content, "images": [], "tag_ids": [_first_tag_id(client)], "reward": 0},
        headers=h,
    )
    assert r.json()["code"] == 0
    return r.json()["data"]["id"]


def _set_embedding(post_id: int, vec) -> None:
    with SessionLocal() as db:
        p = db.get(Post, post_id)
        p.embedding = vec
        db.commit()


@pytest.fixture(autouse=True)
def _clean_query_cache():
    from app.modules.post import service as post_service

    post_service._query_embed_cache.clear()
    yield
    post_service._query_embed_cache.clear()


def test_semantic_beats_literal(client, monkeypatch):
    """语义路径：与查询字面几乎零重叠但向量相近的帖子入选；字面高度重叠但向量正交的落选。"""
    monkeypatch.setattr(gateway, "embed", lambda texts: [[1.0, 0.0]])
    h = _register(client)
    sem_id = _create_post(client, h, "研究生考试英文科目备考方法")  # 与查询字面零重叠、语义同题
    lit_id = _create_post(client, h, "考研英语复习计划")  # 与查询字面高重叠
    _set_embedding(sem_id, [0.99, 0.05])  # 与查询向量 cos≈1
    _set_embedding(lit_id, [0.0, 1.0])  # 与查询向量正交 cos=0

    r = client.get("/api/posts/similar", params={"q": "考研英语怎么复习"})
    items = r.json()["data"]["items"]
    ids = [i["id"] for i in items]
    assert sem_id in ids
    assert lit_id not in ids  # 语义路径下字面重叠不再得分
    score = next(i["similar_score"] for i in items if i["id"] == sem_id)
    assert score >= 0.9


def test_fallback_bigram_when_llm_down(client, monkeypatch):
    """查询向量不可用（LLM 关闭/失败）→ 整轮回退 bigram：字面相似的帖子正常推荐。"""

    def _down(texts):
        raise LLMDegradedError("LLM 未启用（embed）")

    monkeypatch.setattr(gateway, "embed", _down)
    h = _register(client)
    sem_id = _create_post(client, h, "研究生考试英文科目备考方法")
    lit_id = _create_post(client, h, "考研英语复习计划")

    r = client.get("/api/posts/similar", params={"q": "考研英语怎么复习"})
    ids = [i["id"] for i in r.json()["data"]["items"]]
    assert lit_id in ids  # bigram 字面相似入选
    assert sem_id not in ids  # 字面零重叠且无语义路径 → 落选


def test_create_post_computes_embedding_in_background(client, monkeypatch):
    """发帖后后台任务计算语义向量（TestClient 同步执行 BackgroundTasks）。"""
    monkeypatch.setattr(gateway, "embed", lambda texts: [[0.1, 0.2, 0.3]])
    h = _register(client)
    pid = _create_post(client, h, "Python 装饰器怎么写")
    with SessionLocal() as db:
        assert db.get(Post, pid).embedding == [0.1, 0.2, 0.3]


def test_create_post_embedding_failure_silent(client, monkeypatch):
    """向量计算失败静默降级：发帖主流程成功，embedding 保持 NULL。"""

    def _down(texts):
        raise LLMDegradedError("网络错误")

    monkeypatch.setattr(gateway, "embed", _down)
    h = _register(client)
    pid = _create_post(client, h, "Flask 蓝图拆分最佳实践")
    with SessionLocal() as db:
        p = db.get(Post, pid)
        assert p is not None and p.embedding is None
