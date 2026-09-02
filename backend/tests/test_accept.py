"""S6 测试：采纳状态机与知识库 TC-accept 全组。"""

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import (
    Answer,
    CreditAccount,
    GratitudeStat,
    KnowledgeItem,
    Notification,
    Tag,
)
from scripts.seed import run as seed_tags

_seq = iter(range(5_000_000, 6_000_000))


def _user(client, nickname) -> dict:
    r = client.post(
        "/api/auth/register",
        json={"phone": f"138{next(_seq):08d}", "password": "password123", "nickname": nickname},
    )
    return {"Authorization": f"Bearer {r.json()['data']['token']}"}


def _setup(client, answer_count=3) -> tuple[dict, list[dict], int]:
    """建帖 + N 个回答者各交一答，返回 (提问者header, 回答者headers, post_id)。"""
    h = _user(client, "提问者")
    seed_tags()
    with SessionLocal() as db:
        tag_id = db.execute(select(Tag.id)).scalar()
    pid = client.post(
        "/api/posts",
        json={"title": "线性代数秩的问题", "content": "矩阵秩怎么求？", "tag_ids": [tag_id]},
        headers=h,
    ).json()["data"]["id"]
    hs = []
    for i in range(answer_count):
        hi = _user(client, f"回答者{i}")
        client.post(f"/api/posts/{pid}/answers", json={"content": f"回答 {i}"}, headers=hi)
        hs.append(hi)
    return h, hs, pid


def _aids(client, pid) -> list[int]:
    return [a["id"] for a in client.get(f"/api/posts/{pid}").json()["data"]["answers"]]


def test_accept_first_sets_solved_and_kb(client):
    """首采：帖子已解决 + 知识库收录 + 积分 30 + 感谢值三周期 + 通知。"""
    h, hs, pid = _setup(client)
    # 注意：回答列表按 最佳>采纳>点赞>时间倒序 排序，aids[0] 未必是 hs[0] 的回答，
    # 必须按 author_id 定位 hs[0] 的回答再采纳。
    answers = client.get(f"/api/posts/{pid}").json()["data"]["answers"]
    answerer_id = client.get("/api/auth/me", headers=hs[0]).json()["data"]["id"]
    aid = next(a["id"] for a in answers if a["author_id"] == answerer_id)

    r = client.post(f"/api/answers/{aid}/accept", headers=h)
    data = r.json()["data"]
    assert data["post_status"] == 1
    assert data["granted"] == {"credit": 30, "gratitude": 30}

    with SessionLocal() as db:
        assert db.get(KnowledgeItem, pid) is not None
        assert db.get(Answer, aid).is_accepted == 1
        assert db.get(CreditAccount, answerer_id).balance == 80  # 50 注册 + 30
        g = {
            (r.period_type, r.period_key): r.value
            for r in db.execute(
                select(GratitudeStat).where(GratitudeStat.user_id == answerer_id)
            ).scalars()
        }
        assert len(g) == 3 and all(v == 30 for v in g.values())
        n = db.execute(
            select(Notification).where(
                Notification.user_id == answerer_id, Notification.type == 4
            )
        ).scalar_one_or_none()
        assert n is not None


def test_accept_permissions_and_dup(client):
    """非提问者 40301；重复采纳 40907；不存在的回答 40002。"""
    h, hs, pid = _setup(client, answer_count=1)
    aid = _aids(client, pid)[0]
    r = client.post(f"/api/answers/{aid}/accept", headers=hs[0])
    assert r.json()["code"] == 40301
    client.post(f"/api/answers/{aid}/accept", headers=h)
    r = client.post(f"/api/answers/{aid}/accept", headers=h)
    assert r.json()["code"] == 40907
    r = client.post("/api/answers/99999/accept", headers=h)
    assert r.json()["code"] == 40002


def test_accept_limit_three(client):
    """采纳上限 3：第 4 个 40901；知识库仅一条记录。"""
    h, hs, pid = _setup(client, answer_count=4)
    aids = _aids(client, pid)
    for aid in aids[:3]:
        r = client.post(f"/api/answers/{aid}/accept", headers=h)
        assert r.json()["code"] == 0
    r = client.post(f"/api/answers/{aids[3]}/accept", headers=h)
    assert r.json()["code"] == 40901
    with SessionLocal() as db:
        kb = db.execute(
            select(KnowledgeItem).where(KnowledgeItem.post_id == pid)
        ).scalars().all()
        assert len(kb) == 1


def test_set_best_requires_accepted_and_unique(client):
    """set_best：未采纳 40908；已采纳可设且换人先清后置。"""
    h, hs, pid = _setup(client, answer_count=2)
    aids = _aids(client, pid)
    # 未采纳目标
    r = client.post(f"/api/answers/{aids[0]}/set-best", headers=h)
    assert r.json()["code"] == 40908
    # 采纳两个
    client.post(f"/api/answers/{aids[0]}/accept", headers=h)
    client.post(f"/api/answers/{aids[1]}/accept", headers=h)
    r = client.post(f"/api/answers/{aids[0]}/set-best", headers=h)
    assert r.json()["data"] == {"best_answer_id": aids[0]}
    # 换最佳：先清后置，零账务（无新积分/感谢值变动）
    bal_before = {
        u: client.get("/api/credit/balance", headers=hh).json()["data"]["balance"]
        for u, hh in zip(("a", "b"), hs)
    }
    r = client.post(f"/api/answers/{aids[1]}/set-best", headers=h)
    assert r.json()["data"] == {"best_answer_id": aids[1]}
    with SessionLocal() as db:
        assert db.get(Answer, aids[0]).is_best == 0
        assert db.get(Answer, aids[1]).is_best == 1
    bal_after = {
        u: client.get("/api/credit/balance", headers=hh).json()["data"]["balance"]
        for u, hh in zip(("a", "b"), hs)
    }
    assert bal_before == bal_after  # 零账务变动
    # 非提问者
    r = client.post(f"/api/answers/{aids[0]}/set-best", headers=hs[0])
    assert r.json()["code"] == 40301


def test_accept_credit_capped_gratitude_not(client):
    """日封顶截断积分，感谢值不受影响（ARCH §7.1）。"""
    h, hs, pid = _setup(client, answer_count=1)
    aid = _aids(client, pid)[0]
    answerer_id = client.get("/api/auth/me", headers=hs[0]).json()["data"]["id"]
    # 预先灌满日额度：注册 50 + 任务 50 = 100
    from app.modules.credit import service as cs
    from app.modules.credit.sources import CreditSource

    with SessionLocal() as db:
        cs.grant(db, answerer_id, CreditSource.TASK, 50, note="灌满")
        db.commit()
    r = client.post(f"/api/answers/{aid}/accept", headers=h)
    data = r.json()["data"]
    assert data["granted"]["credit"] == 0  # 封顶
    assert data["granted"]["gratitude"] == 30  # 感谢值照常
    with SessionLocal() as db:
        g = db.execute(
            select(GratitudeStat).where(GratitudeStat.user_id == answerer_id)
        ).scalars().all()
        assert all(x.value == 30 for x in g)
        assert db.get(CreditAccount, answerer_id).balance == 100
