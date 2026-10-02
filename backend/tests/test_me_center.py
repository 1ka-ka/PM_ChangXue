"""V1.12 测试：个人中心（我的回答/评论/点赞）+ 他人公开内容 + 主页统计。"""

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import Post, Tag
from scripts.seed import run as seed_tags

_seq = iter(range(8_000_000, 9_000_000))  # 号段隔离：136 前缀仅 llm_gateway 用 6M，8M 空闲


def _user(client, nickname="用户") -> tuple[dict, int]:
    r = client.post(
        "/api/auth/register",
        json={"phone": f"136{next(_seq):08d}", "password": "password123", "nickname": nickname},
    )
    return {"Authorization": f"Bearer {r.json()['data']['token']}"}, r.json()["data"]["user"]["id"]


def _tags() -> list[int]:
    seed_tags()
    with SessionLocal() as db:
        return [t.id for t in db.execute(select(Tag).order_by(Tag.id)).scalars().all()[:3]]


def _setup_data(client):
    """甲发帖 → 乙回答 + 帖评论 + 回答评论 + 点赞（帖/答/评论）。返回 (h甲, uid甲, h乙, uid乙, pid, aid)。"""
    ha, uida = _user(client, "甲")
    hb, uidb = _user(client, "乙")
    tags = _tags()
    pid = client.post(
        "/api/posts",
        json={"title": "GIL 是什么", "content": "Python 的 GIL 具体指什么？", "tag_ids": tags},
        headers=ha,
    ).json()["data"]["id"]
    aid = client.post(
        f"/api/posts/{pid}/answers", json={"content": "全局解释器锁，同一时刻仅一个线程执行字节码。"}, headers=hb
    ).json()["data"]["id"]
    # 乙：帖评论 + 回答评论 + 点赞帖/答/评论
    client.post(
        "/api/comments",
        json={"target_type": 1, "target_id": pid, "content": "同问，蹲个详解", "parent_id": None},
        headers=hb,
    )
    client.post(
        "/api/comments",
        json={"target_type": 2, "target_id": aid, "content": "解释得很清楚", "parent_id": None},
        headers=hb,
    )
    client.post("/api/likes/toggle", json={"target_type": 1, "target_id": pid}, headers=hb)
    # 乙的帖评论被甲点赞（评论 target_type=3）
    with SessionLocal() as db:
        from app.models import Comment

        cid = (
            db.execute(select(Comment).where(Comment.target_type == 1, Comment.target_id == pid)).scalars().first()
        ).id
    client.post("/api/likes/toggle", json={"target_type": 3, "target_id": cid}, headers=ha)
    # 甲点赞乙的回答（乙不自赞）
    client.post("/api/likes/toggle", json={"target_type": 2, "target_id": aid}, headers=ha)
    return ha, uida, hb, uidb, pid, aid


def test_my_answers(client):
    """我的回答：含所属帖标题与采纳状态。"""
    ha, uida, hb, uidb, pid, aid = _setup_data(client)
    r = client.get("/api/account/my-answers", headers=hb)
    data = r.json()["data"]
    assert data["total"] == 1
    item = data["items"][0]
    assert item["post_id"] == pid
    assert item["post_title"] == "GIL 是什么"
    assert item["is_accepted"] is False
    assert item["like_count"] == 1  # 甲点赞
    # 未登录 401
    assert client.get("/api/account/my-answers").status_code == 401


def test_my_comments(client):
    """我的评论：帖评论与回答评论各一条，均能定位所属帖。"""
    ha, uida, hb, uidb, pid, aid = _setup_data(client)
    r = client.get("/api/account/my-comments", headers=hb)
    data = r.json()["data"]
    assert data["total"] == 2
    for c in data["items"]:
        assert c["post_id"] == pid
        assert c["post_title"] == "GIL 是什么"
    types = {c["target_type"] for c in data["items"]}
    assert types == {1, 2}


def test_my_likes(client):
    """我的点赞：乙赞帖；甲赞回答+评论。"""
    ha, uida, hb, uidb, pid, aid = _setup_data(client)
    r = client.get("/api/account/my-likes", headers=hb)
    items = r.json()["data"]["items"]
    assert r.json()["data"]["total"] == 1
    assert items[0]["target_type"] == 1
    assert items[0]["post_id"] == pid
    assert items[0]["author_nickname"] == "甲"
    # 甲的点赞：乙的回答 + 乙的评论
    r = client.get("/api/account/my-likes", headers=ha)
    items = r.json()["data"]["items"]
    tt = {i["target_type"] for i in items}
    assert tt == {2, 3}


def test_user_public_posts_and_answers(client):
    """他人主页：TA 的公开提问/回答（免登录可看）。"""
    ha, uida, hb, uidb, pid, aid = _setup_data(client)
    r = client.get(f"/api/account/users/{uida}/posts")
    assert r.json()["data"]["total"] == 1
    assert r.json()["data"]["items"][0]["title"] == "GIL 是什么"
    r = client.get(f"/api/account/users/{uidb}/answers")
    assert r.json()["data"]["total"] == 1
    assert r.json()["data"]["items"][0]["post_title"] == "GIL 是什么"
    # 用户不存在
    assert client.get("/api/account/users/99999/posts").json()["code"] == 40002


def test_profile_stats(client):
    """主页统计：提问/回答/获赞数 + 注册时间。"""
    ha, uida, hb, uidb, pid, aid = _setup_data(client)
    r = client.get(f"/api/account/users/{uida}")
    data = r.json()["data"]
    assert data["post_count"] == 1
    assert data["answer_count"] == 0
    assert data["like_received"] == 1  # 帖被乙点赞
    assert data["created_at"] is not None
    r = client.get(f"/api/account/users/{uidb}")
    data = r.json()["data"]
    assert data["answer_count"] == 1
    assert data["like_received"] == 1  # 回答被甲点赞


def test_my_likes_deleted_target_skipped(client):
    """点赞目标被删：列表不出现该条（记录被清理或兜底跳过）。"""
    ha, uida, hb, uidb, pid, aid = _setup_data(client)
    client.delete(f"/api/posts/{pid}", headers=ha)
    r = client.get("/api/account/my-likes", headers=hb)
    items = r.json()["data"]["items"]
    assert all(i["target_type"] != 1 for i in items)
