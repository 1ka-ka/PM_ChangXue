"""S0 冒烟测试：应用启动、信封格式、错误码 40001 返回形态。"""


def test_health(client):
    """应用启动冒烟：健康检查返回 code=0。"""
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 0
    assert body["msg"] == "ok"
    assert body["data"]["status"] == "up"


def test_envelope_shape(client):
    """响应信封结构：固定三字段 code/msg/data。"""
    r = client.get("/api/health")
    assert set(r.json().keys()) == {"code", "msg", "data"}


def test_echo_ok(client):
    """连通性：正常参数透传。"""
    r = client.get("/api/echo", params={"n": 5})
    assert r.json() == {"code": 0, "msg": "ok", "data": {"n": 5}}


def test_validation_error_returns_40001(client):
    """参数校验失败：HTTP 200 + code=40001 信封（技术细节文档 §2.1）。"""
    r = client.get("/api/echo")  # 缺少必填参数 n
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 40001
    assert body["data"] is None
    assert "参数错误" in body["msg"]


def test_validation_type_error_returns_40001(client):
    """参数类型错误同样转 40001。"""
    r = client.get("/api/echo", params={"n": "abc"})
    assert r.status_code == 200
    assert r.json()["code"] == 40001
