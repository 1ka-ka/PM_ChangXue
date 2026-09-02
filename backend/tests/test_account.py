"""S2 测试：注册/登录/JWT/资料/头像/个人主页/装扮占位。"""

import io

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import CreditAccount, CreditLog, User

PASSWORD = "password123"
_seq = iter(range(1000))


def _unique_phone() -> str:
    """每个测试用唯一手机号（session 级共享内存库，避免相互污染）。"""
    return f"138{next(_seq):08d}"


def _register(client, phone=None, nickname="小明", password=PASSWORD):
    return client.post(
        "/api/auth/register",
        json={
            "phone": phone or _unique_phone(),
            "password": password,
            "nickname": nickname,
        },
    )


def test_register_success_grants_credits(client):
    """注册成功：返回 token + UserFull，事务内开户赠 50 积分 + 流水。"""
    phone = _unique_phone()
    r = _register(client, phone=phone)
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 0
    token = body["data"]["token"]
    assert token
    user = body["data"]["user"]
    assert user["credit_balance"] == 50
    assert user["phone"] == f"{phone[:3]}****{phone[-4:]}"  # 脱敏
    assert user["gratitude"] == {"week": 0, "month": 0, "total": 0}

    with SessionLocal() as db:
        u = db.execute(select(User).where(User.phone == phone)).scalar_one()
        acct = db.get(CreditAccount, u.id)
        assert acct.balance == 50
        logs = db.execute(select(CreditLog).where(CreditLog.user_id == u.id)).scalars().all()
        assert len(logs) == 1 and logs[0].change == 50


def test_register_duplicate_phone(client):
    """重复注册：40004。"""
    phone = _unique_phone()
    _register(client, phone=phone)
    r = _register(client, phone=phone, nickname="另一个人")
    assert r.json()["code"] == 40004


def test_register_invalid_phone(client):
    """手机号格式错误：40001。"""
    r = _register(client, phone="12345")
    assert r.json()["code"] == 40001


def test_register_weak_password(client):
    """密码强度不足：40001。"""
    r = _register(client, password="short")
    assert r.json()["code"] == 40001


def test_register_sensitive_nickname(client):
    """昵称敏感词：40001。"""
    r = _register(client, nickname="测试敏感词")
    assert r.json()["code"] == 40001
    assert "违禁词" in r.json()["msg"]


def test_login_ok_and_wrong_password(client):
    """登录成功返回 token；错误密码 40101。"""
    phone = _unique_phone()
    _register(client, phone=phone)
    r = client.post("/api/auth/login", json={"phone": phone, "password": PASSWORD})
    assert r.json()["code"] == 0
    r = client.post("/api/auth/login", json={"phone": phone, "password": "wrongpass99"})
    assert r.json()["code"] == 40101


def test_me_requires_valid_token(client):
    """无 token / 坏 token 访问 /auth/me：40102。"""
    r = client.get("/api/auth/me")
    assert r.status_code == 401
    assert r.json()["code"] == 40102
    r = client.get("/api/auth/me", headers={"Authorization": "Bearer bad.token.here"})
    assert r.json()["code"] == 40102


def test_me_ok(client):
    """有效 token：返回 UserFull。"""
    token = _register(client).json()["data"]["token"]
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.json()["code"] == 0
    assert r.json()["data"]["nickname"] == "小明"


def test_login_banned(client):
    """封禁账号登录：40103。"""
    phone = _unique_phone()
    _register(client, phone=phone)
    with SessionLocal() as db:
        u = db.execute(select(User).where(User.phone == phone)).scalar_one()
        u.status = 1
        db.commit()
    r = client.post("/api/auth/login", json={"phone": phone, "password": PASSWORD})
    assert r.json()["code"] == 40103


def test_update_profile(client):
    """更新资料成功；空提交 40001；敏感昵称 40001。"""
    token = _register(client).json()["data"]["token"]
    h = {"Authorization": f"Bearer {token}"}
    r = client.put(
        "/api/account/profile",
        json={"school": "XX大学", "major": "计算机"},
        headers=h,
    )
    assert r.json()["code"] == 0
    assert r.json()["data"]["school"] == "XX大学"
    r = client.put("/api/account/profile", json={}, headers=h)
    assert r.json()["code"] == 40001
    r = client.put(
        "/api/account/profile", json={"nickname": "违规占位词"}, headers=h
    )
    assert r.json()["code"] == 40001


def test_avatar_upload_and_invalid(client):
    """头像上传成功返回 url；伪造扩展名（magic bytes 不符）40005。"""
    token = _register(client).json()["data"]["token"]
    h = {"Authorization": f"Bearer {token}"}

    # 构造 1x1 PNG
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (300, 300), "red").save(buf, "PNG")
    png = buf.getvalue()
    r = client.post(
        "/api/account/avatar",
        files={"file": ("a.png", png, "image/png")},
        headers=h,
    )
    assert r.json()["code"] == 0
    assert r.json()["data"]["url"].startswith("/uploads/")

    # 伪 png（内容是文本）
    r = client.post(
        "/api/account/avatar",
        files={"file": ("fake.png", b"not an image", "image/png")},
        headers=h,
    )
    assert r.json()["code"] == 40005


def test_public_profile_privacy(client):
    """个人主页：本人可见 credit_balance；他人不可见。"""
    token = _register(client).json()["data"]["token"]
    h = {"Authorization": f"Bearer {token}"}
    uid = client.get("/api/auth/me", headers=h).json()["data"]["id"]

    # 本人视角
    r = client.get(f"/api/account/users/{uid}", headers=h)
    data = r.json()["data"]
    assert data["is_self"] is True and data["credit_balance"] == 50

    # 匿名视角
    r = client.get(f"/api/account/users/{uid}")
    data = r.json()["data"]
    assert data["is_self"] is False and "credit_balance" not in data

    # 不存在的用户
    r = client.get("/api/account/users/99999")
    assert r.json()["code"] == 40002


def test_theme_placeholder(client):
    """装扮配置占位：恒返回 theme=null。"""
    r = client.get("/api/account/theme")
    assert r.json() == {"code": 0, "msg": "ok", "data": {"theme": None}}
