"""S4 测试：发帖提问（含悬赏）TC-post 全组。"""

from datetime import datetime, timedelta

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import CreditAccount, Post, Tag
from scripts.seed import run as seed_tags

_seq = iter(range(3_000_000, 4_000_000))


def _user_and_header(client, nickname="发帖人") -> tuple[dict, int]:
    r = client.post(
        "/api/auth/register",
        json={"phone": f"138{next(_seq):08d}", "password": "password123", "nickname": nickname},
    )
    return {"Authorization": f"Bearer {r.json()['data']['token']}"}, r.json()["data"]["user"]["id"]


def _tag_ids(client) -> list[int]:
    """seed 标签并取前三个 id。"""
    seed_tags()
    with SessionLocal() as db:
        return [t.id for t in db.execute(select(Tag).order_by(Tag.id)).scalars().all()[:3]]


def _create(client, h, tags, **kw):
    body = {"title": "高数极限求解问题", "content": "lim x→0 sinx/x 为什么等于 1？", "tag_ids": tags, **kw}
    return client.post("/api/posts", json=body, headers=h)


def test_create_post_basic(client):
    """发帖成功：默认待解决、无悬赏、标签关联。"""
    h, uid = _user_and_header(client)
    tags = _tag_ids(client)
    r = _create(client, h, tags)
    data = r.json()["data"]
    assert data["status"] == 0 and data["reward"] == 0
    assert len(data["tags"]) == 3
    assert data["author_id"] == uid
    assert data["is_liked"] is False and data["is_favorite"] is False


def test_create_post_reward_transaction(client):
    """悬赏发帖：同事务扣分成功；帖子 reward 记录档位。"""
    h, _ = _user_and_header(client)
    tags = _tag_ids(client)
    r = _create(client, h, tags, reward=20)
    assert r.json()["code"] == 0
    pid = r.json()["data"]["id"]
    # 注册赠 50 - 悬赏 20 = 30
    r = client.get("/api/credit/balance", headers=h)
    assert r.json()["data"]["balance"] == 30
    with SessionLocal() as db:
        p = db.get(Post, pid)
        assert p.reward == 20


def test_create_post_reward_insufficient_rollback(client):
    """悬赏超余额：40902 整体回滚（帖子不落库）。"""
    h, uid = _user_and_header(client)
    tags = _tag_ids(client)
    before = client.get("/api/credit/balance", headers=h).json()["data"]["balance"]  # 50
    r = _create(client, h, tags, reward=100)  # 50 < 100
    assert r.json()["code"] == 40902
    assert "50" in r.json()["msg"]
    with SessionLocal() as db:
        count = len(
            db.execute(
                select(Post).where(Post.author_id == uid)
            ).scalars().all()
        )
        assert count == 0  # 整体回滚
    after = client.get("/api/credit/balance", headers=h).json()["data"]["balance"]
    assert after == before


def test_create_post_validation(client):
    """标题缺失/敏感词/无效标签/悬赏非法档位。"""
    h, _ = _user_and_header(client)
    tags = _tag_ids(client)
    r = client.post(
        "/api/posts", json={"title": "", "content": "x", "tag_ids": tags}, headers=h
    )
    assert r.json()["code"] == 40001
    r = _create(client, h, tags, title="测试敏感词求助")
    assert r.json()["code"] == 40003
    r = _create(client, h, [999])
    assert r.json()["code"] == 40001
    r = _create(client, h, tags, reward=33)
    assert r.json()["code"] == 40001


def test_get_detail_increments_view(client):
    """详情：view_count 递增；匿名可访问。"""
    h, _ = _user_and_header(client)
    tags = _tag_ids(client)
    pid = _create(client, h, tags).json()["data"]["id"]
    for _ in range(3):
        client.get(f"/api/posts/{pid}")
    r = client.get(f"/api/posts/{pid}", headers=h)
    assert r.json()["data"]["view_count"] >= 4


def test_get_detail_not_found(client):
    r = client.get("/api/posts/99999")
    assert r.json()["code"] == 40002


def test_update_post_window_and_permission(client):
    """编辑：窗口内成功且 tags 同步；非帖主 40301。"""
    h, _ = _user_and_header(client)
    tags = _tag_ids(client)
    pid = _create(client, h, tags).json()["data"]["id"]
    r = client.put(
        f"/api/posts/{pid}",
        json={"title": "改后的标题", "content": "补充内容", "tag_ids": tags[:2]},
        headers=h,
    )
    assert r.json()["code"] == 0
    assert r.json()["data"]["title"] == "改后的标题"
    assert len(r.json()["data"]["tags"]) == 2
    assert r.json()["data"]["edited"] is True

    h2, _ = _user_and_header(client, "路人")
    r = client.put(
        f"/api/posts/{pid}",
        json={"title": "hijack", "content": "x", "tag_ids": tags},
        headers=h2,
    )
    assert r.json()["code"] == 40301


def test_update_post_window_expired(client):
    """超 15 分钟窗口：40001。"""
    h, _ = _user_and_header(client)
    tags = _tag_ids(client)
    pid = _create(client, h, tags).json()["data"]["id"]
    with SessionLocal() as db:
        p = db.get(Post, pid)
        p.created_at = datetime.now() - timedelta(minutes=16)
        db.commit()
    r = client.put(
        f"/api/posts/{pid}",
        json={"title": "晚了", "content": "x", "tag_ids": tags},
        headers=h,
    )
    assert r.json()["code"] == 40001
    assert "15 分钟" in r.json()["msg"]


def test_delete_post_and_cascade_invisible(client):
    """删除：软删后详情 40002；悬赏不退回。"""
    h, _ = _user_and_header(client)
    tags = _tag_ids(client)
    pid = _create(client, h, tags, reward=20).json()["data"]["id"]
    r = client.delete(f"/api/posts/{pid}", headers=h)
    assert r.json()["code"] == 0
    r = client.get(f"/api/posts/{pid}")
    assert r.json()["code"] == 40002
    # 悬赏不退回：余额仍 30
    assert client.get("/api/credit/balance", headers=h).json()["data"]["balance"] == 30
    # 非帖主删除
    pid2 = _create(client, h, tags).json()["data"]["id"]
    h2, _ = _user_and_header(client, "路人2")
    r = client.delete(f"/api/posts/{pid2}", headers=h2)
    assert r.json()["code"] == 40301


def test_my_posts_filter(client):
    """我的帖子：状态过滤与总数。"""
    h, _ = _user_and_header(client)
    tags = _tag_ids(client)
    _create(client, h, tags, title="帖子A")
    _create(client, h, tags, title="帖子B")
    r = client.get("/api/account/my-posts", headers=h)
    assert r.json()["data"]["total"] == 2
    r = client.get("/api/account/my-posts", params={"status": 0}, headers=h)
    assert r.json()["data"]["total"] == 2  # 均待解决
    # 人工把一帖改为已解决
    pid = r.json()["data"]["items"][0]["id"]
    with SessionLocal() as db:
        p = db.get(Post, pid)
        p.status = 1
        db.commit()
    r = client.get("/api/account/my-posts", params={"status": 1}, headers=h)
    assert r.json()["data"]["total"] == 1
    # 删除的帖子不计入
    client.delete(f"/api/posts/{pid}", headers=h)
    r = client.get("/api/account/my-posts", headers=h)
    assert r.json()["data"]["total"] == 1
