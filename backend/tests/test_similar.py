"""V1.1 测试：相似问答推荐（发帖页防重复 + 详情页相关问题）。"""

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import Tag
from scripts.seed import run as seed_tags

_seq = iter(range(5_000_000, 6_000_000))


def _user(client, nickname) -> dict:
    r = client.post(
        "/api/auth/register",
        json={"phone": f"137{next(_seq):08d}", "password": "password123", "nickname": nickname},
    )
    return {"Authorization": f"Bearer {r.json()['data']['token']}"}


def _tag_id() -> int:
    seed_tags()
    with SessionLocal() as db:
        return db.execute(select(Tag.id).order_by(Tag.id)).scalars().first()


def _post(client, h, title, tag_id, content="正文内容"):
    r = client.post(
        "/api/posts",
        json={"title": title, "content": content, "tag_ids": [tag_id]},
        headers=h,
    )
    assert r.json()["code"] == 0, r.json()
    return r.json()["data"]["id"]


def test_similar_by_query_ranks_and_filters(client):
    """发帖页按标题推荐：相似帖命中、无关帖被阈值过滤、按分数降序。"""
    h = _user(client, "提问者")
    tid = _tag_id()
    p1 = _post(client, h, "FastAPI 依赖注入的最佳实践", tid)
    _post(client, h, "FastAPI 依赖注入如何管理生命周期", tid)
    p_unrelated = _post(client, h, "周末去哪玩比较合适", tid)

    r = client.get("/api/posts/similar", params={"q": "FastAPI 依赖注入最佳实践是什么", "tag_ids": str(tid)})
    data = r.json()["data"]
    ids = [it["id"] for it in data["items"]]

    assert ids[0] == p1  # 最相似排第一
    assert p_unrelated not in ids  # 无关帖（周末玩）被阈值过滤
    scores = [it["similar_score"] for it in data["items"]]
    assert scores == sorted(scores, reverse=True)  # 降序
    assert all(s >= 0.2 for s in scores)  # 阈值
    assert all("id" in it and "title" in it and "tags" in it for it in data["items"])  # PostCard 结构


def test_similar_by_query_tag_bonus(client):
    """标签重合加权：同标签比无标签候选分数更高。"""
    h = _user(client, "提问者")
    seed_tags()
    with SessionLocal() as db:
        tids = db.execute(select(Tag.id).order_by(Tag.id)).scalars().all()[:2]
    _post(client, h, "线性代数矩阵秩怎么求", tids[0])
    _post(client, h, "矩阵的秩计算方法有哪些", tids[1])  # 标题同量级相似但标签不同

    r = client.get(
        "/api/posts/similar",
        params={"q": "矩阵秩求解方法", "tag_ids": str(tids[0])},
    )
    items = r.json()["data"]["items"]
    assert items, "应有推荐结果"
    with_tag = [it for it in items if tids[0] in [t["id"] for t in it["tags"]]]
    without = [it for it in items if tids[0] not in [t["id"] for t in it["tags"]]]
    if with_tag and without:  # 两者都命中时，同标签的应排前
        assert with_tag[0]["similar_score"] >= without[0]["similar_score"]


def test_similar_by_query_empty_and_short(client):
    """无匹配返回空列表；标题过短（<2 字符）转 40001 信封（项目约定 HTTP 200）。"""
    h = _user(client, "提问者")
    tid = _tag_id()
    _post(client, h, "量子力学入门书推荐", tid)

    r = client.get("/api/posts/similar", params={"q": "红烧肉怎么做才好吃不腻"})
    assert r.json()["data"]["items"] == []

    r = client.get("/api/posts/similar", params={"q": "短"})
    assert r.json()["code"] == 40001


def test_similar_of_post_excludes_self(client):
    """详情页相关问题：推荐相似帖且排除自身；不存在帖 40002。"""
    h = _user(client, "提问者")
    tid = _tag_id()
    p1 = _post(client, h, "C++ 智能指针 unique_ptr 怎么用", tid)
    p2 = _post(client, h, "C++ unique_ptr 与 shared_ptr 区别", tid)
    _post(client, h, "求推荐好看的纪录片", tid)

    r = client.get(f"/api/posts/{p1}/similar")
    data = r.json()["data"]
    ids = [it["id"] for it in data["items"]]
    assert p1 not in ids  # 排除自身
    assert p2 in ids  # 相似帖命中
    titles = [it["title"] for it in data["items"]]
    assert all("纪录片" not in t for t in titles)  # 无关帖被过滤

    r = client.get("/api/posts/999999/similar")
    assert r.json()["code"] == 40002


def test_similar_ignores_deleted(client):
    """软删帖不参与推荐。"""
    h = _user(client, "提问者")
    tid = _tag_id()
    p1 = _post(client, h, "考研英语复习计划怎么制定", tid)
    _post(client, h, "考研英语复习规划求助", tid)

    client.delete(f"/api/posts/{p1}", headers=h)
    r = client.get("/api/posts/similar", params={"q": "考研英语复习计划"})
    ids = [it["id"] for it in r.json()["data"]["items"]]
    assert p1 not in ids
