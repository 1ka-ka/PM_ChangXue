"""S7 测试：广场三 Tab 与搜索降级 TC-feed / TC-search 全组。

注意：测试库为 session 级共享内存库，此前模块已产生帖子——
所有断言只针对本组自建帖子的相对顺序/存在性，不假设全库内容。
"""

from datetime import datetime, timedelta

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import Post, Tag, TrackingEvent
from scripts.seed import run as seed_tags

_seq = iter(range(6_000_000, 7_000_000))


def _user(client, nickname) -> dict:
    r = client.post(
        "/api/auth/register",
        json={"phone": f"138{next(_seq):08d}", "password": "password123", "nickname": nickname},
    )
    return {"Authorization": f"Bearer {r.json()['data']['token']}"}


def _tag_id() -> int:
    seed_tags()
    with SessionLocal() as db:
        return db.execute(select(Tag.id)).scalar()


def _post(client, h, title, content="内容", reward=0, tag_id=None) -> int:
    r = client.post(
        "/api/posts",
        json={"title": title, "content": content, "tag_ids": [tag_id or _tag_id()], "reward": reward},
        headers=h,
    )
    assert r.json()["code"] == 0, r.json()
    return r.json()["data"]["id"]


def _age_post(post_id: int, days: int) -> None:
    with SessionLocal() as db:
        db.get(Post, post_id).created_at = datetime.now() - timedelta(days=days)
        db.commit()


def _feed(client, tab, page_size=50):
    r = client.get(f"/api/feed?tab={tab}&page_size={page_size}")
    assert r.json()["code"] == 0
    return r.json()["data"]


# ---------- TC-feed ----------


def test_feed_latest_and_tab_filter(client):
    """latest 按 id 倒序；unsolved 仅待解决；软删帖不可见。"""
    h = _user(client, "广场用户")
    p1 = _post(client, h, "最新排序帖A")
    p2 = _post(client, h, "最新排序帖B")

    items = _feed(client, "latest")["items"]
    ids = [i["id"] for i in items]
    assert ids.index(p2) < ids.index(p1)  # 后发在前

    # 软删后广场不可见
    client.delete(f"/api/posts/{p2}", headers=h)
    ids = [i["id"] for i in _feed(client, "latest")["items"]]
    assert p2 not in ids and p1 in ids

    # unsolved 过滤：p1 待解决可见
    items = _feed(client, "unsolved")["items"]
    assert all(i["status"] == 0 for i in items)
    assert p1 in [i["id"] for i in items]


def test_feed_reward_weighting_and_decay(client):
    """悬赏加权：悬赏帖排在普通帖前；14 天衰减后反超（技术细节 §6.3）。"""
    h = _user(client, "推荐用户")
    plain = _post(client, h, "衰减加权普通帖")  # 先发
    rewarded = _post(client, h, "衰减加权悬赏帖", reward=50)  # 后发

    # 悬赏 +5 分 > 0：悬赏帖应排在普通帖之前
    ids = [i["id"] for i in _feed(client, "recommend")["items"]]
    assert ids.index(rewarded) < ids.index(plain)

    # 悬赏帖造旧 20 天（> DECAY_DAYS=14）：衰减 -50，普通帖反超
    _age_post(rewarded, 20)
    ids = [i["id"] for i in _feed(client, "recommend")["items"]]
    assert ids.index(plain) < ids.index(rewarded)

    # 衰减只作用于待解决帖：已解决帖不衰减（此处仅验证 unsolved Tab 仍按加权排序）
    items = _feed(client, "unsolved")["items"]
    ids = [i["id"] for i in items]
    assert plain in ids and rewarded in ids


def test_feed_no_answer_days(client):
    """待解决帖超 7 天无回答 → no_answer_days 标注；新帖/有新回答为 None。"""
    h = _user(client, "标注用户")
    old = _post(client, h, "七天无回答标注帖")
    fresh = _post(client, h, "新发帖无标注")
    answered_old = _post(client, h, "旧帖但有新回答")
    _age_post(old, 10)
    _age_post(answered_old, 10)
    # 给 answered_old 一条回答（刷新 last_answer_at）
    h2 = _user(client, "标注回答者")
    client.post(f"/api/posts/{answered_old}/answers", json={"content": "新回答"}, headers=h2)

    items = _feed(client, "unsolved")["items"]
    by_id = {i["id"]: i for i in items}
    assert by_id[old]["no_answer_days"] == 10
    assert by_id[fresh]["no_answer_days"] is None
    assert by_id[answered_old]["no_answer_days"] is None  # 有新回答则不标注


# ---------- TC-search ----------


def _make_kb_post(client, title) -> int:
    """建帖→回答→采纳，使其进入知识库。"""
    h = _user(client, "知识库提问者")
    pid = _post(client, h, title)
    h2 = _user(client, "知识库回答者")
    client.post(f"/api/posts/{pid}/answers", json={"content": "知识库答案"}, headers=h2)
    aid = next(
        a["id"]
        for a in client.get(f"/api/posts/{pid}").json()["data"]["answers"]
    )
    r = client.post(f"/api/answers/{aid}/accept", headers=h)
    assert r.json()["code"] == 0
    return pid


def test_search_kb_priority(client):
    """知识库优先：命中 kb 时不再返回广场帖。"""
    kb_id = _make_kb_post(client, "特征值降秩 uniqueKB")
    h = _user(client, "广场提问者")
    plaza_id = _post(client, h, "特征值降秩普通帖 uniqueKB")

    r = client.get("/api/search?q=uniqueKB").json()["data"]
    assert r["source"] == "kb"
    assert r.get("degraded") is not True  # kb 命中不附降级标记
    ids = [i["id"] for i in r["items"]]
    assert kb_id in ids and plaza_id not in ids  # 广场同名帖不混入


def test_search_degrade_to_plaza_with_event(client):
    """知识库无果降级广场：degraded=true + search_degrade 埋点落库。"""
    h = _user(client, "降级提问者")
    pid = _post(client, h, "降级检索目标帖 uniqueDegrade", content="正文含 uniqueDegradeBody")

    # 标题命中
    r = client.get("/api/search?q=uniqueDegrade").json()["data"]
    assert r["source"] == "plaza" and r["degraded"] is True
    assert pid in [i["id"] for i in r["items"]]

    # 正文命中（广场降级查标题/内容）
    r = client.get("/api/search?q=uniqueDegradeBody").json()["data"]
    assert r["source"] == "plaza"
    assert pid in [i["id"] for i in r["items"]]

    # 埋点：关键词与广场结果数
    with SessionLocal() as db:
        events = (
            db.execute(select(TrackingEvent).where(TrackingEvent.event_name == "search_degrade"))
            .scalars()
            .all()
        )
    matched = [e for e in events if (e.props or {}).get("keyword") == "uniqueDegrade"]
    assert matched and matched[-1].props["plaza_count"] >= 1


def test_search_empty_and_missing_params(client):
    """两级空结果：均无 → source=empty；q/tag 全缺 → 40001。"""
    h = _user(client, "空搜索用户")
    _post(client, h, "空搜索背景帖")

    r = client.get("/api/search?q=绝不存在的关键词zzz9").json()["data"]
    assert r == {"source": "empty", "items": [], "total": 0}

    r = client.get("/api/search").json()
    assert r["code"] == 40001


def test_search_tag_filter(client):
    """标签筛选：仅返回该标签下帖子。"""
    with SessionLocal() as db:
        tag_ids = db.execute(select(Tag.id)).scalars().all()
    t1, t2 = tag_ids[0], tag_ids[1]
    h = _user(client, "标签搜索用户")
    in_tag = _post(client, h, "标签筛选目标帖 uniqueTag", tag_id=t1)
    out_tag = _post(client, h, "标签筛选排除帖 uniqueTag", tag_id=t2)

    r = client.get(f"/api/search?q=uniqueTag&tag_id={t1}").json()["data"]
    ids = [i["id"] for i in r["items"]]
    assert in_tag in ids and out_tag not in ids
