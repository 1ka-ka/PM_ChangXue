"""S5 测试：回答与双层评论互动 TC-answer/comment/like 全组。"""

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import Answer, Comment, Post, Tag
from scripts.seed import run as seed_tags

_seq = iter(range(4_000_000, 5_000_000))


def _user(client, nickname) -> dict:
    r = client.post(
        "/api/auth/register",
        json={"phone": f"138{next(_seq):08d}", "password": "password123", "nickname": nickname},
    )
    return {"Authorization": f"Bearer {r.json()['data']['token']}"}


def _setup_post(client) -> tuple[dict, int]:
    h = _user(client, "提问者")
    seed_tags()
    with SessionLocal() as db:
        tag_id = db.execute(select(Tag.id)).scalar()
    r = client.post(
        "/api/posts",
        json={"title": "Python GIL 问题", "content": "GIL 对多线程的影响？", "tag_ids": [tag_id]},
        headers=h,
    )
    return h, r.json()["data"]["id"]


def _answer(client, h, post_id, content="GIL 使多线程无法并行执行字节码…"):
    return client.post(
        f"/api/posts/{post_id}/answers", json={"content": content}, headers=h
    )


def test_create_answer_and_counters(client):
    """回答成功：answer_count+1、last_answer_at 更新、详情 answers 挂载。"""
    h, pid = _setup_post(client)
    h2 = _user(client, "回答者")
    r = _answer(client, h2, pid)
    assert r.json()["code"] == 0
    aid = r.json()["data"]["id"]
    assert r.json()["data"]["is_accepted"] is False
    r = client.get(f"/api/posts/{pid}")
    data = r.json()["data"]
    assert data["answer_count"] == 1
    assert len(data["answers"]) == 1
    assert data["answers"][0]["id"] == aid


def test_create_answer_self_and_duplicate(client):
    """自问自答 40904；重复回答 40904。"""
    h, pid = _setup_post(client)
    r = _answer(client, h, pid)
    assert r.json()["code"] == 40904
    h2 = _user(client, "回答者B")
    _answer(client, h2, pid)
    r = _answer(client, h2, pid, content="再答一次")
    assert r.json()["code"] == 40904
    r = _answer(client, h2, 99999)
    assert r.json()["code"] == 40002


def test_update_delete_answer_locks(client):
    """编辑/删除：非作者 40301；采纳锁定（模拟）40905/40906。"""
    h, pid = _setup_post(client)
    h2 = _user(client, "回答者C")
    aid = _answer(client, h2, pid).json()["data"]["id"]

    # 非作者编辑
    r = client.put(f"/api/answers/{aid}", json={"content": "hack"}, headers=h)
    assert r.json()["code"] == 40301
    # 正常编辑
    r = client.put(f"/api/answers/{aid}", json={"content": "修改后的回答"}, headers=h2)
    assert r.json()["code"] == 0
    # 模拟已采纳锁定
    with SessionLocal() as db:
        a = db.get(Answer, aid)
        a.is_accepted = 1
        db.commit()
    r = client.put(f"/api/answers/{aid}", json={"content": "x"}, headers=h2)
    assert r.json()["code"] == 40905
    r = client.delete(f"/api/answers/{aid}", headers=h2)
    assert r.json()["code"] == 40906


def test_delete_answer_counter(client):
    """删除回答：answer_count 减 1；详情不再展示。"""
    h, pid = _setup_post(client)
    h2 = _user(client, "回答者D")
    aid = _answer(client, h2, pid).json()["data"]["id"]
    r = client.delete(f"/api/answers/{aid}", headers=h2)
    assert r.json()["code"] == 0
    data = client.get(f"/api/posts/{pid}").json()["data"]
    assert data["answer_count"] == 0 and data["answers"] == []


def test_comment_two_layers(client):
    """双层评论：根评论+回复成功；三层 40909。"""
    h, pid = _setup_post(client)
    h2 = _user(client, "评论者")
    r = client.post(
        "/api/comments",
        json={"target_type": 1, "target_id": pid, "content": "蹲一个答案"},
        headers=h2,
    )
    root_id = r.json()["data"]["id"]
    assert r.json()["code"] == 0
    # 回复根评论
    r = client.post(
        "/api/comments",
        json={
            "target_type": 1, "target_id": pid, "content": "同问",
            "parent_id": root_id, "reply_to_user_id": r.json()["data"]["author_id"],
        },
        headers=h2,
    )
    assert r.json()["code"] == 0
    reply_id = r.json()["data"]["id"]
    # 三层封顶
    r = client.post(
        "/api/comments",
        json={"target_type": 1, "target_id": pid, "content": "三层", "parent_id": reply_id},
        headers=h2,
    )
    assert r.json()["code"] == 40909
    # 树结构验证
    data = client.get(f"/api/posts/{pid}").json()["data"]
    assert len(data["comments"]) == 1
    assert len(data["comments"][0]["replies"]) == 1


def test_comment_on_answer_and_delete_cascade(client):
    """对回答评论；删除根评论级联软删回复。"""
    h, pid = _setup_post(client)
    h2 = _user(client, "回答者E")
    aid = _answer(client, h2, pid).json()["data"]["id"]
    h3 = _user(client, "评论者F")
    r = client.post(
        "/api/comments",
        json={"target_type": 2, "target_id": aid, "content": "讲得清楚"},
        headers=h3,
    )
    root_id = r.json()["data"]["id"]
    client.post(
        "/api/comments",
        json={"target_type": 2, "target_id": aid, "content": "+1", "parent_id": root_id},
        headers=h3,
    )
    # 删除根评论 → 回复级联隐藏
    r = client.delete(f"/api/comments/{root_id}", headers=h3)
    assert r.json()["code"] == 0
    with SessionLocal() as db:
        roots = (
            db.execute(
                select(Comment).where(Comment.target_type == 2, Comment.target_id == aid)
            )
            .scalars()
            .all()
        )
        assert all(c.deleted_at is not None for c in roots)
    # 非作者删除
    r = client.post(
        "/api/comments",
        json={"target_type": 2, "target_id": aid, "content": "another"},
        headers=h2,
    )
    cid = r.json()["data"]["id"]
    r = client.delete(f"/api/comments/{cid}", headers=h)
    assert r.json()["code"] == 40301


def test_like_toggle_all_targets(client):
    """点赞 toggle：帖/回答/评论均可，幂等往返，计数正确。"""
    h, pid = _setup_post(client)
    h2 = _user(client, "回答者G")
    aid = _answer(client, h2, pid).json()["data"]["id"]
    r = client.post(
        "/api/comments",
        json={"target_type": 2, "target_id": aid, "content": "赞"},
        headers=h2,
    )
    cid = r.json()["data"]["id"]

    # 帖子点赞/取消
    r = client.post("/api/likes/toggle", json={"target_type": 1, "target_id": pid}, headers=h2)
    assert r.json()["data"] == {"liked": True, "like_count": 1}
    r = client.post("/api/likes/toggle", json={"target_type": 1, "target_id": pid}, headers=h2)
    assert r.json()["data"] == {"liked": False, "like_count": 0}
    # 回答
    r = client.post("/api/likes/toggle", json={"target_type": 2, "target_id": aid}, headers=h)
    assert r.json()["data"]["liked"] is True
    # 评论
    r = client.post("/api/likes/toggle", json={"target_type": 3, "target_id": cid}, headers=h)
    assert r.json()["data"]["liked"] is True
    # 无效目标
    r = client.post("/api/likes/toggle", json={"target_type": 1, "target_id": 99999}, headers=h)
    assert r.json()["code"] == 40002


def test_favorite_toggle_and_comment_blocked(client):
    """收藏：帖/回答可收藏；评论 40910。"""
    h, pid = _setup_post(client)
    h2 = _user(client, "回答者H")
    aid = _answer(client, h2, pid).json()["data"]["id"]
    r = client.post("/api/favorites/toggle", json={"target_type": 1, "target_id": pid}, headers=h2)
    assert r.json()["data"]["favorited"] is True
    r = client.post("/api/favorites/toggle", json={"target_type": 1, "target_id": pid}, headers=h2)
    assert r.json()["data"]["favorited"] is False
    r = client.post("/api/favorites/toggle", json={"target_type": 2, "target_id": aid}, headers=h2)
    assert r.json()["data"]["favorited"] is True
    # 评论不可收藏
    r = client.post(
        "/api/comments",
        json={"target_type": 1, "target_id": pid, "content": "c"},
        headers=h2,
    )
    cid = r.json()["data"]["id"]
    r = client.post("/api/favorites/toggle", json={"target_type": 3, "target_id": cid}, headers=h2)
    assert r.json()["code"] == 40910


def test_answer_sorting(client):
    """排序：最佳 > 采纳 > 点赞数。"""
    h, pid = _setup_post(client)
    ha, hb, hc = (_user(client, n) for n in ("答A", "答B", "答C"))
    a1 = _answer(client, ha, pid, "回答一").json()["data"]["id"]
    a2 = _answer(client, hb, pid, "回答二").json()["data"]["id"]
    a3 = _answer(client, hc, pid, "回答三").json()["data"]["id"]
    # a3 两个赞，a2 一个赞，a1 采纳
    client.post("/api/likes/toggle", json={"target_type": 2, "target_id": a3}, headers=ha)
    client.post("/api/likes/toggle", json={"target_type": 2, "target_id": a3}, headers=hb)
    client.post("/api/likes/toggle", json={"target_type": 2, "target_id": a2}, headers=ha)
    with SessionLocal() as db:
        db.get(Answer, a1).is_accepted = 1
        db.commit()
    answers = client.get(f"/api/posts/{pid}").json()["data"]["answers"]
    assert [a["id"] for a in answers] == [a1, a3, a2]
