"""V1.4 测试：短信验证码（发送频控 / 一次性校验 / 短信登录 / 找回密码，dev provider）。"""

from app.core.database import SessionLocal
from app.models import SmsCode

_seq = iter(range(8_000_000, 9_000_000))


def _phone() -> str:
    return f"135{next(_seq):08d}"


def _register(client, phone: str, nickname="短信用户") -> dict:
    r = client.post(
        "/api/auth/register",
        json={"phone": phone, "password": "password123", "nickname": nickname},
    )
    assert r.json()["code"] == 0, r.json()
    return {"Authorization": f"Bearer {r.json()['data']['token']}"}


def _send(client, phone: str, scene: int) -> str:
    r = client.post("/api/auth/sms/send", json={"phone": phone, "scene": scene})
    assert r.json()["code"] == 0, r.json()
    code = r.json()["data"]["debug_code"]  # dev provider 必回传
    assert isinstance(code, str) and len(code) == 6
    return code


# ---- 发送：频控 / 日限额 / 注册状态预校验 ----


def test_sms_send_success_with_debug_code(client):
    """dev 模式发送成功：响应带 6 位 debug_code（真实 provider 不回传）。"""
    phone = _phone()
    _register(client, phone)
    _send(client, phone, scene=2)  # 断言在 _send 内


def test_sms_send_interval_throttle(client):
    """60s 频控：同手机号同场景连发 → 40914。"""
    phone = _phone()
    _register(client, phone)
    _send(client, phone, scene=2)
    r = client.post("/api/auth/sms/send", json={"phone": phone, "scene": 2})
    assert r.json()["code"] == 40914


def test_sms_send_daily_limit(client, monkeypatch):
    """日限额：当日第 SMS_DAILY_LIMIT+1 条 → 40915（monkeypatch 上限=1）。"""
    from app.core.config import settings

    phone = _phone()
    _register(client, phone)
    monkeypatch.setattr(settings, "SMS_DAILY_LIMIT", 1)
    _send(client, phone, scene=2)
    r = client.post("/api/auth/sms/send", json={"phone": phone, "scene": 3})
    assert r.json()["code"] == 40915


def test_sms_send_unregistered_phone(client):
    """登录/找回场景要求已注册：未注册手机号 → 40001。"""
    r = client.post("/api/auth/sms/send", json={"phone": _phone(), "scene": 2})
    assert r.json()["code"] == 40001
    assert "未注册" in r.json()["msg"]


# ---- 短信登录 ----


def test_sms_login_full_flow(client):
    """短信登录全链路：发码 → 登录拿 token → /auth/me 可用。"""
    phone = _phone()
    _register(client, phone)
    code = _send(client, phone, scene=2)
    r = client.post("/api/auth/sms/login", json={"phone": phone, "code": code})
    assert r.json()["code"] == 0, r.json()
    token = r.json()["data"]["token"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.json()["code"] == 0


def test_sms_login_wrong_code(client):
    """验证码错误 → 40104，且错误码不消耗（正确码仍可登录）。"""
    phone = _phone()
    _register(client, phone)
    code = _send(client, phone, scene=2)
    r = client.post("/api/auth/sms/login", json={"phone": phone, "code": "000000" if code != "000000" else "111111"})
    assert r.json()["code"] == 40104
    # 正确码仍可用（错误尝试不消耗）
    r = client.post("/api/auth/sms/login", json={"phone": phone, "code": code})
    assert r.json()["code"] == 0


def test_sms_login_code_single_use(client):
    """验证码一次性：登录成功后同码再用 → 40104。"""
    phone = _phone()
    _register(client, phone)
    code = _send(client, phone, scene=2)
    r = client.post("/api/auth/sms/login", json={"phone": phone, "code": code})
    assert r.json()["code"] == 0
    r = client.post("/api/auth/sms/login", json={"phone": phone, "code": code})
    assert r.json()["code"] == 40104


def test_sms_login_expired_code(client):
    """过期验证码 → 40104（直接改库把 expired_at 拨到过去）。"""
    phone = _phone()
    _register(client, phone)
    code = _send(client, phone, scene=2)
    with SessionLocal() as db:
        row = db.query(SmsCode).filter(SmsCode.phone == phone).order_by(SmsCode.id.desc()).first()
        from datetime import datetime, timedelta

        row.expired_at = datetime.now() - timedelta(seconds=1)
        db.commit()
    r = client.post("/api/auth/sms/login", json={"phone": phone, "code": code})
    assert r.json()["code"] == 40104


# ---- 找回密码 ----


def test_reset_password_flow(client):
    """找回密码：发码 → 重置 → 旧密码失败 / 新密码成功。"""
    phone = _phone()
    _register(client, phone)
    code = _send(client, phone, scene=3)
    r = client.post(
        "/api/auth/reset-password",
        json={"phone": phone, "code": code, "new_password": "newpassword456"},
    )
    assert r.json()["code"] == 0, r.json()

    r = client.post("/api/auth/login", json={"phone": phone, "password": "password123"})
    assert r.json()["code"] == 40101
    r = client.post("/api/auth/login", json={"phone": phone, "password": "newpassword456"})
    assert r.json()["code"] == 0


def test_reset_password_code_single_use(client):
    """重置码一次性：重置成功后同码再重置 → 40104。"""
    phone = _phone()
    _register(client, phone)
    code = _send(client, phone, scene=3)
    r = client.post(
        "/api/auth/reset-password",
        json={"phone": phone, "code": code, "new_password": "first12345"},
    )
    assert r.json()["code"] == 0
    r = client.post(
        "/api/auth/reset-password",
        json={"phone": phone, "code": code, "new_password": "second67890"},
    )
    assert r.json()["code"] == 40104


def test_scene_isolation(client):
    """场景隔离：scene=3 的码不能用于 scene=2 登录。"""
    phone = _phone()
    _register(client, phone)
    code = _send(client, phone, scene=3)  # 找回码
    r = client.post("/api/auth/sms/login", json={"phone": phone, "code": code})
    assert r.json()["code"] == 40104
