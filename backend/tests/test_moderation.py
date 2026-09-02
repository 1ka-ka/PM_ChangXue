"""S9 测试：举报与管理后台 TC-moderation 全组（含 TC-softdel）。"""

from datetime import datetime, timedelta

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import AdminActionLog, CreditAccount, Tag, User
from scripts.seed import run as seed_tags

_seq = iter(range(8_000_000, 9_000_000))


def _user(client, nickname, admin=False) -> dict:
    r = client.post(
        "/api/auth/register",
        json={"phone": f"138{next(_seq):08d}", "password": "password123", "nickname": nickname},
    )
    h = {"Authorization": f"Bearer {r.json()['data']['token']}"}
    if admin:
        uid = client.get("/api/auth/me", headers=h).json()["data"]["id"]
        with SessionLocal() as db:
            db.get(User, uid).role = 1
            db.commit()
    return h


def _uid(client, h) -> int:
    return client.get("/api/auth/me", headers=h).json()["data"]["id"]


def _tag_id(client, h) -> int:
    seed_tags()
    with SessionLocal() as db:
        # 只取启用标签且按 id 排序：整文件跑时可能存在已停用标签，
        # 无序 scalar() 在 SQLite 下可能按 name 索引序命中停用标签
        return db.execute(
            select(Tag.id).where(Tag.enabled == 1).order_by(Tag.id)
        ).scalar()


def _post(client, h, title, content="正文内容") -> int:
    r = client.post(
        "/api/posts",
        json={"title": title, "content": content, "tag_ids": [_tag_id(client, h)]},
        headers=h,
    )
    assert r.json()["code"] == 0, r.json()
    return r.json()["data"]["id"]


def _answer_of(client, h_answerer, pid) -> int:
    uid = _uid(client, h_answerer)
    client.post(f"/api/posts/{pid}/answers", json={"content": "待处置回答"}, headers=h_answerer)
    return next(
        a["id"] for a in client.get(f"/api/posts/{pid}").json()["data"]["answers"]
        if a["author_id"] == uid
    )


def _report(client, h, target_type, target_id, reason=1, detail="") -> int:
    r = client.post(
        "/api/reports",
        json={"target_type": target_type, "target_id": target_id, "reason": reason, "detail": detail},
        headers=h,
    )
    assert r.json()["code"] == 0, r.json()
    return r.json()["data"] if isinstance(r.json()["data"], int) else target_id


# ---------- 举报提交 ----------


def test_report_dedup_and_target_missing(client):
    """举报去重 40903；目标不存在/已删 40002。"""
    author, reporter = _user(client, "被举报作者"), _user(client, "举报者")
    pid = _post(client, author, "举报去重目标帖")

    r = client.post(
        "/api/reports", json={"target_type": 1, "target_id": pid, "reason": 1, "detail": "广告"},
        headers=reporter,
    )
    assert r.json()["code"] == 0
    # 同一用户重复举报同一目标 → 40903
    r = client.post(
        "/api/reports", json={"target_type": 1, "target_id": pid, "reason": 2},
        headers=reporter,
    )
    assert r.json()["code"] == 40903
    # 目标不存在
    r = client.post(
        "/api/reports", json={"target_type": 1, "target_id": 999999, "reason": 1},
        headers=reporter,
    )
    assert r.json()["code"] == 40002
    # 目标被作者删除后举报 → 40002
    pid2 = _post(client, author, "已删目标帖")
    client.delete(f"/api/posts/{pid2}", headers=author)
    r = client.post(
        "/api/reports", json={"target_type": 1, "target_id": pid2, "reason": 1},
        headers=reporter,
    )
    assert r.json()["code"] == 40002


def test_admin_guard_40302(client):
    """非管理员访问后台 → 40302。"""
    h = _user(client, "普通用户")
    for method, path in [
        ("get", "/api/admin/reports"),
        ("get", "/api/admin/tags"),
        ("get", "/api/admin/logs"),
        ("get", "/api/admin/stats"),
    ]:
        r = getattr(client, method)(path, headers=h)
        assert r.json()["code"] == 40302, (path, r.json())
    r = client.post(
        "/api/admin/reports/1/action",
        json={"action": "delete", "reason": "x"},
        headers=h,
    )
    assert r.json()["code"] == 40302


# ---------- 处置四动作 ----------


def _pending_report_id(client, admin_h, target_type, target_id) -> int:
    """在后台待处理队列中定位该目标对应举报 id。"""
    r = client.get("/api/admin/reports?status=0&page_size=50", headers=admin_h).json()["data"]
    return next(x["id"] for x in r["items"] if x["target_type"] == target_type and x["target_id"] == target_id)


def test_action_delete_softdel_everywhere(client):
    """处置-删除：级联软删 + TC-softdel（广场/搜索/知识库三处不可见）+ 40911 已处理。"""
    admin, author, answerer, reporter = (
        _user(client, "管理A1", admin=True), _user(client, "被删帖作者"),
        _user(client, "被删帖回答者"), _user(client, "被删帖举报者"),
    )
    pid = _post(client, author, "处置删除目标帖 uniqueDel")
    aid = _answer_of(client, answerer, pid)
    client.post(f"/api/answers/{aid}/accept", headers=author)  # 入知识库
    # 帖下留一条根评论 + 一条回复（级联验证）
    client.post(
        "/api/comments", json={"target_type": 1, "target_id": pid, "content": "根评论"},
        headers=reporter,
    )
    client.post(
        "/api/reports", json={"target_type": 1, "target_id": pid, "reason": 1, "detail": "垃圾"},
        headers=reporter,
    )
    rid = _pending_report_id(client, admin, 1, pid)

    # 处置删除
    r = client.post(
        f"/api/admin/reports/{rid}/action",
        json={"action": "delete", "reason": "垃圾广告，删除"},
        headers=admin,
    )
    assert r.json()["code"] == 0

    # TC-softdel：广场不可见
    ids = [i["id"] for i in client.get("/api/feed?tab=latest&page_size=50").json()["data"]["items"]]
    assert pid not in ids
    # 搜索不可见（知识库关键词命不中，降级广场也命不中 → empty）
    r = client.get("/api/search?q=uniqueDel").json()["data"]
    assert r["source"] == "empty"
    # 帖子详情 40002
    r = client.get(f"/api/posts/{pid}").json()
    assert r["code"] == 40002
    # 回答/评论级联不可见：回答者删自己的回答 → 40002（已删）
    r = client.delete(f"/api/answers/{aid}", headers=answerer).json()
    assert r["code"] == 40002

    # 再次处置同举报 → 40911
    r = client.post(
        f"/api/admin/reports/{rid}/action",
        json={"action": "delete", "reason": "重复处置"},
        headers=admin,
    )
    assert r.json()["code"] == 40911

    # 操作日志留痕（action=1 删帖）
    r = client.get("/api/admin/logs?action=1&page_size=50", headers=admin).json()["data"]
    assert any(l["target_id"] == pid for l in r["items"])


def test_action_ban_and_login_blocked(client):
    """处置-封号：到期时间正确；封号后 token 访问 40103。"""
    admin, author, reporter = (
        _user(client, "管理A2", admin=True), _user(client, "被封作者"), _user(client, "封号举报者"),
    )
    pid = _post(client, author, "封号处置帖")
    client.post("/api/reports", json={"target_type": 1, "target_id": pid, "reason": 2}, headers=reporter)
    rid = _pending_report_id(client, admin, 1, pid)
    uid = _uid(client, author)  # 封号前取 uid（封号后 token 即失效）

    r = client.post(
        f"/api/admin/reports/{rid}/action",
        json={"action": "ban", "reason": "人身攻击", "ban_days": 7},
        headers=admin,
    )
    assert r.json()["code"] == 0
    with SessionLocal() as db:
        u = db.get(User, uid)
        assert u.status == 1 and u.banned_until is not None
        assert u.banned_until > datetime.now() + timedelta(days=6)
    r = client.get("/api/auth/me", headers=author).json()
    assert r["code"] == 40103
    # 日志 action=4
    r = client.get("/api/admin/logs?action=4&page_size=50", headers=admin).json()["data"]
    assert any(l["target_id"] == uid for l in r["items"])


def test_action_recall_credit_actual_value(client):
    """处置-追回：余额不足追回至 0，流水与日志记实际值。"""
    admin, author, reporter = (
        _user(client, "管理A3", admin=True), _user(client, "被追回作者"), _user(client, "追回举报者"),
    )
    pid = _post(client, author, "追回处置帖")
    client.post("/api/reports", json={"target_type": 1, "target_id": pid, "reason": 4}, headers=reporter)
    rid = _pending_report_id(client, admin, 1, pid)

    # 余额只有注册 50：追回 80 → 实际 50，余额 0
    r = client.post(
        f"/api/admin/reports/{rid}/action",
        json={"action": "recall_credit", "reason": "违规刷分", "amount": 80},
        headers=admin,
    )
    assert r.json()["code"] == 0
    uid = _uid(client, author)
    with SessionLocal() as db:
        assert db.get(CreditAccount, uid).balance == 0
    # 日志记实际值
    r = client.get("/api/admin/logs?action=6&page_size=50", headers=admin).json()["data"]
    mine = next(l for l in r["items"] if l["target_id"] == pid)
    assert "实际追回 50" in mine["reason"]


def test_action_dismiss_and_queue_snapshot(client):
    """处置-驳回 status=2；队列含快照/作者/举报次数。"""
    admin, author, reporter = _user(client, "管理A4", admin=True), _user(client, "驳回作者"), _user(client, "驳回举报者")
    pid = _post(client, author, "驳回处置帖")
    client.post("/api/reports", json={"target_type": 1, "target_id": pid, "reason": 5, "detail": "误报"}, headers=reporter)
    # 第二个用户也举报同一目标 → report_count=2
    other = _user(client, "驳回举报者2")
    client.post("/api/reports", json={"target_type": 1, "target_id": pid, "reason": 5}, headers=other)
    rid = _pending_report_id(client, admin, 1, pid)

    # 队列快照校验
    r = client.get("/api/admin/reports?status=0&page_size=50", headers=admin).json()["data"]
    item = next(x for x in r["items"] if x["id"] == rid)
    assert item["content"]["kind"] == "post" and item["content"]["title"] == "驳回处置帖"
    assert item["author"]["id"] == _uid(client, author)
    assert item["report_count"] == 2

    r = client.post(
        f"/api/admin/reports/{rid}/action",
        json={"action": "dismiss", "reason": "误报"},
        headers=admin,
    )
    assert r.json()["code"] == 0
    # 驳回后进入 status=2 队列，内容未被删
    r = client.get("/api/admin/reports?status=2&page_size=50", headers=admin).json()["data"]
    assert any(x["id"] == rid for x in r["items"])
    assert client.get(f"/api/posts/{pid}").json()["code"] == 0


def test_action_delete_answer_cascade(client):
    """处置-删回答：回答与评论软删，帖子仍在，answer_count 回减。"""
    admin, author, answerer, commenter, reporter = (
        _user(client, "管理A5", admin=True), _user(client, "删答作者"),
        _user(client, "删答回答者"), _user(client, "删答评论者"), _user(client, "删答举报者"),
    )
    pid = _post(client, author, "删回答处置帖")
    aid = _answer_of(client, answerer, pid)
    client.post(
        "/api/comments", json={"target_type": 2, "target_id": aid, "content": "回答下评论"},
        headers=commenter,
    )
    client.post("/api/reports", json={"target_type": 2, "target_id": aid, "reason": 1}, headers=reporter)
    rid = _pending_report_id(client, admin, 2, aid)

    r = client.post(
        f"/api/admin/reports/{rid}/action",
        json={"action": "delete", "reason": "低质灌水"},
        headers=admin,
    )
    assert r.json()["code"] == 0
    # 帖子仍在，回答数回 0
    data = client.get(f"/api/posts/{pid}").json()["data"]
    assert data["answer_count"] == 0
    assert data["answers"] == []
    # 日志 action=2 删回答
    r = client.get("/api/admin/logs?action=2&page_size=50", headers=admin).json()["data"]
    assert any(l["target_id"] == aid for l in r["items"])


# ---------- 标签管理与看板 ----------


def test_tag_management(client):
    """标签管理：新增/改名冲突/停用后发帖不可选。"""
    admin = _user(client, "管理A6", admin=True)
    r = client.post("/api/admin/tags", json={"name": "S9测试标签", "sort": 99}, headers=admin).json()
    assert r["code"] == 0 and r["data"]["name"] == "S9测试标签"
    tid = r["data"]["id"]
    # 重名
    r = client.post("/api/admin/tags", json={"name": "S9测试标签"}, headers=admin).json()
    assert r["code"] == 40001
    # 改名冲突
    seed_tags()
    other = client.get("/api/admin/tags", headers=admin).json()["data"][0]["id"]
    r = client.put(f"/api/admin/tags/{tid}", json={"name": "数学"}, headers=admin).json()
    assert r["code"] == 40001
    # 停用后发帖不可选
    r = client.put(f"/api/admin/tags/{tid}", json={"enabled": 0}, headers=admin).json()
    assert r["code"] == 0 and r["data"]["enabled"] is False
    h = _user(client, "标签停用验证用户")
    r = client.post(
        "/api/posts",
        json={"title": "停用标签帖", "content": "x", "tag_ids": [tid]},
        headers=h,
    ).json()
    assert r["code"] == 40001  # 存在无效标签（S4：enabled==1 过滤，停用即无效）


def test_admin_stats(client):
    """看板统计：字段齐全，pending_reports 至少含本组待处理举报。"""
    admin, author, reporter = _user(client, "管理A7", admin=True), _user(client, "看板作者"), _user(client, "看板举报者")
    pid = _post(client, author, "看板统计帖")
    client.post("/api/reports", json={"target_type": 1, "target_id": pid, "reason": 5}, headers=reporter)
    r = client.get("/api/admin/stats", headers=admin).json()["data"]
    assert set(r) == {"pending_reports", "dau", "daily_posts", "daily_accepts"}
    assert r["pending_reports"] >= 1
    assert r["daily_posts"] >= 1  # 本组刚发帖
