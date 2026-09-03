"""V1.7 私信测试：发送/会话列表/未读/游标已读/校验与权限。"""

from app.core.database import SessionLocal
from app.models import DmConversation, User

PASSWORD = "password123"
# 独立号段（137）：避开 test_account(138) 与 test_credit(139，其内部直接建 User 也占号）
_seq = iter(range(1_000_000, 2_000_000))


def _unique_phone() -> str:
    return f"137{next(_seq):08d}"


def _register(client, nickname="用户"):
    r = client.post(
        "/api/auth/register",
        json={"phone": _unique_phone(), "password": PASSWORD, "nickname": nickname},
    )
    token = r.json()["data"]["token"]
    uid = r.json()["data"]["user"]["id"]
    return {"Authorization": f"Bearer {token}"}, uid


def test_send_and_conversation_flow(client):
    """A→B 发送：B 会话列表含对方/摘要/未读 1；拉消息后未读清零；双向同会话。"""
    ha, a_id = _register(client, "甲方")
    hb, b_id = _register(client, "乙方")

    # B 未读为 0
    r = client.get("/api/messages/unread-count", headers=hb)
    assert r.json()["data"] == {"count": 0}

    r = client.post("/api/messages", json={"to_user_id": b_id, "content": "同学你好"}, headers=ha)
    assert r.json()["code"] == 0
    conv_id = r.json()["data"]["conversation_id"]

    # B 未读 1；会话列表一条，含对方信息与摘要
    r = client.get("/api/messages/unread-count", headers=hb)
    assert r.json()["data"] == {"count": 1}
    r = client.get("/api/messages/conversations", headers=hb)
    data = r.json()["data"]
    assert data["total"] == 1
    item = data["items"][0]
    assert item["conversation_id"] == conv_id
    assert item["peer"]["id"] == a_id and item["peer"]["nickname"] == "甲方"
    assert item["last_content"] == "同学你好"
    assert item["unread"] == 1

    # B 回复 → 同一会话
    r = client.post("/api/messages", json={"to_user_id": a_id, "content": "你好呀"}, headers=hb)
    assert r.json()["data"]["conversation_id"] == conv_id

    # A 视角：B 的回复未读 1
    r = client.get("/api/messages/unread-count", headers=ha)
    assert r.json()["data"] == {"count": 1}

    # B 拉取消息（倒序）→ 自己未读清零
    r = client.get(f"/api/messages/conversations/{conv_id}", headers=hb)
    msgs = r.json()["data"]["items"]
    assert [m["content"] for m in msgs] == ["你好呀", "同学你好"]
    r = client.get("/api/messages/unread-count", headers=hb)
    assert r.json()["data"] == {"count": 0}


def test_send_validations(client):
    """给自己发 40001；不存在接收方 40002；空白/超长 40001；敏感词 40003。"""
    ha, a_id = _register(client, "校验者")
    hb, b_id = _register(client, "收件人")

    r = client.post("/api/messages", json={"to_user_id": a_id, "content": "自言自语"}, headers=ha)
    assert r.json()["code"] == 40001

    r = client.post("/api/messages", json={"to_user_id": 99999, "content": "hi"}, headers=ha)
    assert r.json()["code"] == 40002

    r = client.post("/api/messages", json={"to_user_id": b_id, "content": "   "}, headers=ha)
    assert r.json()["code"] == 40001

    r = client.post(
        "/api/messages", json={"to_user_id": b_id, "content": "x" * 501}, headers=ha
    )
    assert r.json()["code"] == 40001

    r = client.post(
        "/api/messages", json={"to_user_id": b_id, "content": "测试敏感词"}, headers=ha
    )
    assert r.json()["code"] == 40003


def test_conversation_access_control(client):
    """未登录 401；非会话成员访问 40002；会话不存在 40002。"""
    ha, a_id = _register(client, "成员A")
    hb, b_id = _register(client, "成员B")
    hc, _ = _register(client, "路人C")

    r = client.post("/api/messages", json={"to_user_id": b_id, "content": "在吗"}, headers=ha)
    conv_id = r.json()["data"]["conversation_id"]

    r = client.get("/api/messages/conversations")
    assert r.status_code == 401

    r = client.get(f"/api/messages/conversations/{conv_id}", headers=hc)
    assert r.json()["code"] == 40002

    r = client.get("/api/messages/conversations/99999", headers=ha)
    assert r.json()["code"] == 40002


def test_multiple_conversations_order_and_pagination(client):
    """多会话按 updated_at 倒序；消息分页。"""
    ha, a_id = _register(client, "主用户")
    hb, b_id = _register(client, "乙")
    hc, c_id = _register(client, "丙")

    client.post("/api/messages", json={"to_user_id": b_id, "content": "第一条"}, headers=ha)
    client.post("/api/messages", json={"to_user_id": c_id, "content": "第二条"}, headers=ha)

    r = client.get("/api/messages/conversations", headers=ha)
    data = r.json()["data"]
    assert data["total"] == 2
    assert data["items"][0]["peer"]["nickname"] == "丙"  # 最近活跃在前

    # 会话内 6 条消息，page_size=4 分两页（倒序）
    conv_id = data["items"][0]["conversation_id"]
    for i in range(4):
        client.post("/api/messages", json={"to_user_id": c_id, "content": f"补充{i}"}, headers=ha)
    r = client.get(f"/api/messages/conversations/{conv_id}?page_size=4", headers=ha)
    page1 = r.json()["data"]
    assert page1["total"] == 5  # 1 + 4
    assert len(page1["items"]) == 4
    r = client.get(f"/api/messages/conversations/{conv_id}?page_size=4&page=2", headers=ha)
    assert len(r.json()["data"]["items"]) == 1


def test_conversation_pair_normalized(client):
    """会话双方归一化（a<b）：双向发送同一对用户仅一会话。"""
    ha, a_id = _register(client, "甲")
    hb, b_id = _register(client, "乙")
    lo, hi = min(a_id, b_id), max(a_id, b_id)

    r = client.post("/api/messages", json={"to_user_id": b_id, "content": "一"}, headers=ha)
    conv_id = r.json()["data"]["conversation_id"]
    r = client.post("/api/messages", json={"to_user_id": a_id, "content": "二"}, headers=hb)
    assert r.json()["data"]["conversation_id"] == conv_id

    with SessionLocal() as db:
        from sqlalchemy import select

        conv = db.execute(
            select(DmConversation).where(DmConversation.id == conv_id)
        ).scalar_one()
        assert conv.user_a_id == lo and conv.user_b_id == hi


def test_soft_deleted_peer_cannot_receive(client):
    """接收方被软删：40002。"""
    from datetime import datetime

    from sqlalchemy import select

    ha, a_id = _register(client, "发件人")
    _hb, b_id = _register(client, "待删除")

    with SessionLocal() as db:
        u = db.execute(select(User).where(User.id == b_id)).scalar_one()
        u.deleted_at = datetime.now()
        db.commit()

    r = client.post("/api/messages", json={"to_user_id": b_id, "content": "在吗"}, headers=ha)
    assert r.json()["code"] == 40002
