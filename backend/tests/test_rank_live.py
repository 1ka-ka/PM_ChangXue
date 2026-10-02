"""V1.14 测试：助人榜多维化——回答数/采纳数日/周/月实时榜 + accepted_at 采纳发生时间。

号段：134+3M（138 前缀随机段已被 test_moderation/test_notify_rank 等占用，独占 134 段避撞）。
共享内存库注意：其余模块的当日回答/采纳也会出现在实时榜，断言只针对本用例用户的精确值与相对名次。
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.core.database import SessionLocal
from app.models import Answer, Tag
from scripts.seed import run as seed_tags

_seq = iter(range(3_000_000, 4_000_000))


@pytest.fixture(autouse=True)
def _wide_top_n(monkeypatch):
    """放宽 TOP N：共享内存库含其他模块的当日回答/采纳，避免精确值断言被 TOP 10 截断挤出。"""
    monkeypatch.setattr(settings, "RANK_TOP_N", 500)


def _user(client, nickname) -> dict:
    r = client.post(
        "/api/auth/register",
        json={"phone": f"134{next(_seq):08d}", "password": "password123", "nickname": nickname},
    )
    return {"Authorization": f"Bearer {r.json()['data']['token']}"}


def _uid(client, h) -> int:
    return client.get("/api/auth/me", headers=h).json()["data"]["id"]


def _tag_id() -> int:
    seed_tags()
    with SessionLocal() as db:
        return db.execute(select(Tag.id).where(Tag.enabled == 1).order_by(Tag.id)).scalar()


def _post(client, h, title) -> int:
    r = client.post(
        "/api/posts",
        json={"title": title, "content": "内容", "tag_ids": [_tag_id()]},
        headers=h,
    )
    return r.json()["data"]["id"]


def _answer_of(client, h_answerer, pid) -> int:
    uid = _uid(client, h_answerer)
    client.post(f"/api/posts/{pid}/answers", json={"content": "实时榜回答"}, headers=h_answerer)
    return next(
        a["id"]
        for a in client.get(f"/api/posts/{pid}").json()["data"]["answers"]
        if a["author_id"] == uid
    )


def _ranks(client, metric: str, period: str) -> dict:
    r = client.get("/api/ranks", params={"metric": metric, "period": period})
    assert r.json()["code"] == 0
    return r.json()["data"]


# ---------- 实时榜：回答数 / 采纳数 ----------


def test_live_rank_answers_and_accepts(client):
    """回答数日榜按 created_at 计数；采纳数按 accepted_at 计数；名次按值降序。"""
    asker = _user(client, "实时榜提问者")
    a, b = _user(client, "实时榜甲"), _user(client, "实时榜乙")
    pid1 = _post(client, asker, "实时榜帖一")
    pid2 = _post(client, asker, "实时榜帖二")
    a1 = _answer_of(client, a, pid1)
    _answer_of(client, a, pid2)
    _answer_of(client, b, pid1)
    client.post(f"/api/answers/{a1}/accept", headers=asker)

    # 回答数日榜：甲 2 / 乙 1，甲名次在前
    r = _ranks(client, "answers", "day")
    assert r["settling"] is False
    assert r["period"] == datetime.now().strftime("%Y-%m-%d")
    by_uid = {i["user"]["id"]: i for i in r["items"]}
    uid_a, uid_b = _uid(client, a), _uid(client, b)
    assert by_uid[uid_a]["value"] == 2 and by_uid[uid_b]["value"] == 1
    assert by_uid[uid_a]["rank"] < by_uid[uid_b]["rank"]

    # 采纳数日榜：甲 1（今日被采纳），乙未上榜
    r = _ranks(client, "accepts", "day")
    by_uid = {i["user"]["id"]: i for i in r["items"]}
    assert by_uid[uid_a]["value"] == 1
    assert uid_b not in by_uid

    # 周/月实时榜同样包含当期数据
    for period in ("week", "month"):
        r = _ranks(client, "answers", period)
        by_uid = {i["user"]["id"]: i["value"] for i in r["items"]}
        assert by_uid[uid_a] == 2 and by_uid[uid_b] == 1
        r = _ranks(client, "accepts", period)
        by_uid = {i["user"]["id"]: i["value"] for i in r["items"]}
        assert by_uid[uid_a] == 1


def test_accepts_counted_by_accept_time(client):
    """采纳数按采纳发生时间计：旧回答今日被采纳 → 计入今日采纳榜，不计入今日回答榜。"""
    asker = _user(client, "旧答提问者")
    a = _user(client, "旧答甲")
    pid = _post(client, asker, "旧回答帖")
    aid = _answer_of(client, a, pid)

    # 回答发布时间改到 40 天前（必然落在上周且上月）
    with SessionLocal() as db:
        ans = db.get(Answer, aid)
        ans.created_at = datetime.now() - timedelta(days=40)
        db.commit()

    client.post(f"/api/answers/{aid}/accept", headers=asker)

    # 采纳发生时间落库
    with SessionLocal() as db:
        assert db.get(Answer, aid).accepted_at is not None

    uid_a = _uid(client, a)
    # 日/月回答榜均不含（回答发布于 40 天前）
    for period in ("day", "month"):
        r = _ranks(client, "answers", period)
        assert uid_a not in {i["user"]["id"] for i in r["items"]}
    # 日/月采纳榜均含（采纳发生在今天）
    for period in ("day", "month"):
        r = _ranks(client, "accepts", period)
        by_uid = {i["user"]["id"]: i["value"] for i in r["items"]}
        assert by_uid[uid_a] == 1


# ---------- 参数校验与兼容 ----------


def test_gratitude_metric_period_validation(client):
    """感谢值仅周/月（日榜 40001）；默认参数等价原接口（gratitude+week）。"""
    r = client.get("/api/ranks", params={"metric": "gratitude", "period": "day"})
    assert r.json()["code"] == 40001

    # 无参默认 = 感谢值周榜（向后兼容）
    r = client.get("/api/ranks")
    assert r.json()["code"] == 0
    d = r.json()["data"]
    assert "items" in d and "settling" in d

    # 非法 metric/period 由 pattern 校验拒绝（全局处理器转 40001 信封）
    assert client.get("/api/ranks", params={"metric": "bad"}).json()["code"] == 40001
    assert client.get("/api/ranks", params={"period": "year"}).json()["code"] == 40001
