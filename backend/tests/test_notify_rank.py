"""S8 测试：通知中心与助人榜 TC-notify / TC-rank 全组。"""

from datetime import datetime, timedelta

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import Notification, RankSnapshot, Tag
from app.modules.rank import service as rank_service
from scripts.seed import run as seed_tags

_seq = iter(range(7_000_000, 8_000_000))


def _user(client, nickname) -> dict:
    r = client.post(
        "/api/auth/register",
        json={"phone": f"138{next(_seq):08d}", "password": "password123", "nickname": nickname},
    )
    return {"Authorization": f"Bearer {r.json()['data']['token']}"}


def _tag_id() -> int:
    seed_tags()
    with SessionLocal() as db:
        # 只取启用标签（整跑时其他模块可能停用标签，无序查询可能命中）
        return db.execute(select(Tag.id).where(Tag.enabled == 1).order_by(Tag.id)).scalar()


def _post(client, h, title) -> int:
    r = client.post(
        "/api/posts",
        json={"title": title, "content": "内容", "tag_ids": [_tag_id()]},
        headers=h,
    )
    return r.json()["data"]["id"]


def _answer_of(client, h_answerer, pid) -> int:
    """h_answerer 在 pid 下提交的回答 id（按 author 定位）。"""
    uid = client.get("/api/auth/me", headers=h_answerer).json()["data"]["id"]
    client.post(f"/api/posts/{pid}/answers", json={"content": "回答内容"}, headers=h_answerer)
    return next(
        a["id"]
        for a in client.get(f"/api/posts/{pid}").json()["data"]["answers"]
        if a["author_id"] == uid
    )


def _my_notifications(client, h) -> list[dict]:
    return client.get("/api/notifications", headers=h).json()["data"]["items"]


# ---------- TC-notify：五类通知 ----------


def test_notification_types_generated(client):
    """五类通知生成与直达参数：被回答/被评论/被回复/被采纳/被点赞。"""
    asker, answerer, third = _user(client, "提问者N"), _user(client, "回答者N"), _user(client, "路人N")
    pid = _post(client, asker, "通知链路帖")
    aid = _answer_of(client, answerer, pid)

    # 1 被回答 → 提问者收到，target=(1, pid)
    items = _my_notifications(client, asker)
    n1 = next(n for n in items if n["type"] == 1)
    assert n1["target_type"] == 1 and n1["target_id"] == pid
    assert n1["actor"]["nickname"] == "回答者N"
    assert n1["is_read"] is False

    # 2 被评论 → 回答者收到（评论挂在回答上），target=(2, aid)
    client.post(
        "/api/comments",
        json={"target_type": 2, "target_id": aid, "content": "评论你的回答"},
        headers=third,
    )
    n2 = next(n for n in _my_notifications(client, answerer) if n["type"] == 2)
    assert n2["target_type"] == 2 and n2["target_id"] == aid

    # 3 被回复 → 根评论作者（third）收到，target=(3, root_id)
    with SessionLocal() as db:
        from app.models import Comment

        root_id = (
            db.execute(
                select(Comment.id).where(Comment.target_type == 2, Comment.target_id == aid)
            )
            .scalars()
            .first()
        )
    client.post(
        "/api/comments",
        json={
            "target_type": 2, "target_id": aid, "content": "回复你的评论",
            "parent_id": root_id, "reply_to_user_id": None,
        },
        headers=asker,
    )
    n3 = next(n for n in _my_notifications(client, third) if n["type"] == 3)
    assert n3["target_type"] == 3 and n3["target_id"] == root_id

    # 4 被采纳 → 回答者收到（S6 已实现，此处验证直达参数）
    client.post(f"/api/answers/{aid}/accept", headers=asker)
    n4 = next(n for n in _my_notifications(client, answerer) if n["type"] == 4)
    assert n4["target_type"] == 2 and n4["target_id"] == aid

    # 5 被点赞 → 提问者收到（点赞帖子），target=(1, pid)
    client.post("/api/likes/toggle", json={"target_type": 1, "target_id": pid}, headers=third)
    n5 = next(n for n in _my_notifications(client, asker) if n["type"] == 5)
    assert n5["target_type"] == 1 and n5["target_id"] == pid


def test_notification_no_self_notify_and_unlike(client):
    """自赞/自评不产生通知；取消点赞不产生通知。"""
    h = _user(client, "自互动用户")
    pid = _post(client, h, "自互动帖")
    client.post("/api/likes/toggle", json={"target_type": 1, "target_id": pid}, headers=h)
    client.post(
        "/api/comments",
        json={"target_type": 1, "target_id": pid, "content": "自评论"},
        headers=h,
    )
    assert _my_notifications(client, h) == []

    # 取消点赞不通知
    other = _user(client, "他人用户")
    client.post("/api/likes/toggle", json={"target_type": 1, "target_id": pid}, headers=other)
    client.post("/api/likes/toggle", json={"target_type": 1, "target_id": pid}, headers=other)
    likes = [n for n in _my_notifications(client, h) if n["type"] == 5]
    assert len(likes) == 1  # 仅第一次点赞


def test_unread_count_and_read_all(client):
    """未读计数 + 全部已读 + 99+ 语义值。"""
    asker, other = _user(client, "计数提问者"), _user(client, "计数他人")
    pid = _post(client, asker, "未读计数帖")
    client.post(f"/api/posts/{pid}/answers", json={"content": "回答"}, headers=other)

    r = client.get("/api/notifications/unread-count", headers=asker).json()["data"]
    assert r["count"] == 1

    client.post("/api/notifications/read-all", headers=asker)
    r = client.get("/api/notifications/unread-count", headers=asker).json()["data"]
    assert r["count"] == 0
    assert all(n["is_read"] for n in _my_notifications(client, asker))

    # 99+ 语义值：直插 130 条未读
    with SessionLocal() as db:
        for i in range(130):
            db.add(
                Notification(
                    user_id=_uid(client, asker), type=5, actor_id=_uid(client, other),
                    target_type=1, target_id=pid,
                )
            )
        db.commit()
    r = client.get("/api/notifications/unread-count", headers=asker).json()["data"]
    assert r["count"] == 100  # >99 → 语义值 100


def _uid(client, h) -> int:
    return client.get("/api/auth/me", headers=h).json()["data"]["id"]


def test_invalid_marked_on_delete(client):
    """软删联动：删帖/删回答/删评论后相关通知 invalid=1 且不计未读。"""
    asker, answerer, third = _user(client, "失效提问者"), _user(client, "失效回答者"), _user(client, "失效路人")
    pid = _post(client, asker, "失效标记帖")
    aid = _answer_of(client, answerer, pid)
    client.post("/api/likes/toggle", json={"target_type": 2, "target_id": aid}, headers=third)

    # 删除回答 → 回答者名下指向 (2, aid) 的通知（被评论/被点赞类）失效
    client.delete(f"/api/answers/{aid}", headers=answerer)
    # 删帖 → 提问者名下指向 (1, pid) 的通知（被回答）失效
    client.delete(f"/api/posts/{pid}", headers=asker)

    # 注意：测试库为 session 级共享，须按本用例用户的 user_id 过滤（其他模块通知不相关）
    asker_uid, answerer_uid = _uid(client, asker), _uid(client, answerer)
    with SessionLocal() as db:
        rows = db.execute(
            select(Notification).where(
                Notification.user_id.in_([asker_uid, answerer_uid]),
                Notification.target_id.in_([pid, aid]),
                Notification.target_type.in_([1, 2]),
            )
        ).scalars().all()
    assert rows and all(r.invalid == 1 for r in rows)

    # 失效通知不计入未读
    for h in (asker, answerer):
        r = client.get("/api/notifications/unread-count", headers=h).json()["data"]
        assert r["count"] == 0


def test_banned_user_login_40103(client):
    """封禁用户访问 40103（S2 实现，S8 回归）。"""
    from datetime import datetime as dt

    h = _user(client, "待封禁用户")
    uid = _uid(client, h)
    with SessionLocal() as db:
        from app.models import User

        u = db.get(User, uid)
        u.status = 1
        u.banned_until = dt.now() + timedelta(days=1)
        db.commit()
    r = client.get("/api/notifications", headers=h)
    assert r.json()["code"] == 40103


# ---------- TC-rank：结算与查询 ----------


def _accept_for(client, asker_h, answerer_h, pid) -> None:
    """answerer 回答并被采纳 → 感谢值 +30。"""
    aid = _answer_of(client, answerer_h, pid)
    r = client.post(f"/api/answers/{aid}/accept", headers=asker_h)
    assert r.json()["code"] == 0


def test_settle_snapshot_correctness(client):
    """结算快照正确性（V1.15 语义）：settle 写 rank_snapshot 作历史存档；榜单 API 为当期实时。"""
    a, b, c = _user(client, "榜单甲"), _user(client, "榜单乙"), _user(client, "榜单丙")
    asker = _user(client, "榜单提问者")
    # 本周采纳：甲 3 次(90)、乙 2 次(60)——共享库中其他模块用户本周感谢值多为并列 30，
    # 拉开差距以保证进入 TOP N 断言稳定
    for i in range(3):
        _accept_for(client, asker, a, _post(client, asker, f"榜单本周帖A{i}"))
    for i in range(2):
        _accept_for(client, asker, b, _post(client, asker, f"榜单本周帖B{i}"))

    # 上周感谢值：直插 gratitude_stat（甲 90 / 丙 30）
    now = datetime.now()
    prev_week = rank_service.prev_keys(now)[1]
    prev_month = rank_service.prev_keys(now)[2]
    with SessionLocal() as db:
        from app.models import GratitudeStat

        db.merge(GratitudeStat(user_id=_uid(client, a), period_type=1, period_key=prev_week, value=90))
        db.merge(GratitudeStat(user_id=_uid(client, c), period_type=1, period_key=prev_week, value=30))
        db.merge(GratitudeStat(user_id=_uid(client, a), period_type=2, period_key=prev_month, value=90))
        db.commit()

    # 结算上周 → rank_snapshot 历史存档（共享库可能含其他模块同周期数据，只断言本用例用户）
    with SessionLocal() as db:
        rank_service.settle(db, 1, prev_week)
        rows = db.execute(
            select(RankSnapshot).where(
                RankSnapshot.period_type == 1, RankSnapshot.period_key == prev_week
            )
        ).scalars().all()
    a_id, c_id = _uid(client, a), _uid(client, c)
    mine_a = [r for r in rows if r.user_id == a_id]
    mine_c = [r for r in rows if r.user_id == c_id]
    assert len(mine_a) == 1 and mine_a[0].value == 90 and mine_a[0].rank == 1  # 甲上周 90 居首
    assert len(mine_c) == 1 and mine_c[0].value == 30 and mine_c[0].rank == 2  # 丙 30 次之

    # 榜单 API（V1.15 起当期实时）：无需结算即出本周数据，settling 恒 False
    r = client.get("/api/ranks?period=week").json()["data"]
    cur_week = rank_service.week_key(now)
    assert r["settling"] is False and r["period"] == cur_week
    values = {i["user"]["id"]: i["value"] for i in r["items"]}
    assert values.get(a_id) == 90 and values.get(_uid(client, b)) == 60


def test_settle_idempotent_and_retry_fallback(client):
    """结算幂等（重跑不重复）；月榜当期实时：当期无快照也不回落上期。"""
    a = _user(client, "幂等甲")
    now = datetime.now()
    prev_week = rank_service.prev_keys(now)[1]
    uid_a = _uid(client, a)
    with SessionLocal() as db:
        from app.models import GratitudeStat

        db.merge(GratitudeStat(user_id=uid_a, period_type=1, period_key=prev_week, value=60))
        db.commit()
        rank_service.settle(db, 1, prev_week)
        rank_service.settle(db, 1, prev_week)  # 重跑
        rows = db.execute(
            select(RankSnapshot).where(
                RankSnapshot.period_type == 1, RankSnapshot.period_key == prev_week
            )
        ).scalars().all()
    assert len(rows) >= 1  # 共享库含其他用户同周期数据
    # 幂等：重跑不产生同一用户的重复快照，且名次唯一
    assert len({r.user_id for r in rows}) == len(rows)
    assert len({r.rank for r in rows}) == len(rows)
    mine = [r for r in rows if r.user_id == uid_a]
    assert len(mine) == 1 and mine[0].value == 60

    # V1.15 语义：月榜当期实时，恒不回落上期、不 settling
    r = client.get("/api/ranks?period=month").json()["data"]
    cur_month = rank_service.month_key(now)
    assert r["settling"] is False and r["period"] == cur_month
