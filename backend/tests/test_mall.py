"""V1.8 商城测试：商品列表/兑换闭环（扣分+减库存+记录）/库存与下架/积分不足。"""

import pytest

from app.core.database import SessionLocal
from app.models import MallExchange, MallProduct
from app.modules.credit import service as credit_service
from app.modules.credit.sources import CreditSource

PASSWORD = "password123"
# 独立号段（136）：避开 test_account(138) / test_credit(139) / test_dm(137)
_seq = iter(range(1_000_000, 2_000_000))


def _unique_phone() -> str:
    return f"136{next(_seq):08d}"


def _register(client, nickname="用户"):
    r = client.post(
        "/api/auth/register",
        json={"phone": _unique_phone(), "password": PASSWORD, "nickname": nickname},
    )
    token = r.json()["data"]["token"]
    uid = r.json()["data"]["user"]["id"]
    return {"Authorization": f"Bearer {token}"}, uid


_created_ids: list[int] = []


@pytest.fixture(autouse=True)
def _cleanup_products():
    yield
    with SessionLocal() as db:
        for pid in _created_ids:
            p = db.get(MallProduct, pid)
            if p is not None:
                db.delete(p)
        db.commit()
    _created_ids.clear()


def _make_product(**kw) -> int:
    """建测试商品（默认虚拟 50 分不限量），登记待清理，返回 id。"""
    defaults = dict(
        name="测试商品", description="单元测试专用", price=50,
        stock=-1, type=1, enabled=1,
    )
    defaults.update(kw)
    with SessionLocal() as db:
        p = MallProduct(**defaults)
        db.add(p)
        db.commit()
        _created_ids.append(p.id)
        return p.id


def _top_up(uid: int, amount: int = 1000):
    """直接发测试积分（绕过日封顶）。"""
    with SessionLocal() as db:
        credit_service.grant(
            db, uid, CreditSource.TASK, amount, apply_daily_cap=False, note="测试充值"
        )
        db.commit()


def test_exchange_virtual_product_full_flow(client):
    """虚拟商品兑换：即完成（status=2）+ 扣分流水 source=7 + 兑换记录。"""
    pid = _make_product(name="虚拟头衔", price=50)
    h, uid = _register(client)
    _top_up(uid, 100)

    r = client.get("/api/credit/balance", headers=h)
    assert r.json()["data"]["balance"] == 150  # 注册 50 + 充值 100

    r = client.post("/api/mall/exchange", json={"product_id": pid}, headers=h)
    data = r.json()["data"]
    assert data["status"] == 2 and data["cost"] == 50
    assert data["product_name"] == "虚拟头衔"

    # 余额扣减 + 流水（source=7 商城兑换，ref 指向兑换记录）
    r = client.get("/api/credit/balance", headers=h)
    assert r.json()["data"]["balance"] == 100
    r = client.get("/api/credit/logs", headers=h)
    log = next(l for l in r.json()["data"]["items"] if l["source"] == 7)
    assert log["change"] == -50 and log["ref_id"] == data["exchange_id"]

    # 兑换记录列表
    r = client.get("/api/mall/exchanges", headers=h)
    assert r.json()["data"]["total"] == 1
    item = r.json()["data"]["items"][0]
    assert item["product_name"] == "虚拟头衔" and item["status"] == 2


def test_exchange_physical_stock_decrement(client):
    """实物商品：待发货（status=1）；限量库存递减至 0 后 40916。"""
    pid = _make_product(name="贴纸包", price=10, stock=2, type=2)
    h, uid = _register(client)

    for _ in range(2):
        r = client.post("/api/mall/exchange", json={"product_id": pid}, headers=h)
        assert r.json()["data"]["status"] == 1

    with SessionLocal() as db:
        assert db.get(MallProduct, pid).stock == 0

    r = client.post("/api/mall/exchange", json={"product_id": pid}, headers=h)
    assert r.json()["code"] == 40916

    # 两条待发货记录
    r = client.get("/api/mall/exchanges", headers=h)
    assert r.json()["data"]["total"] == 2


def test_exchange_insufficient_credit_rollback(client):
    """积分不足 40902：无兑换记录、库存不变、余额不变。"""
    pid = _make_product(name="奢侈品", price=999, stock=3, type=2)
    h, uid = _register(client)  # 余额 50

    r = client.post("/api/mall/exchange", json={"product_id": pid}, headers=h)
    assert r.json()["code"] == 40902

    with SessionLocal() as db:
        assert db.get(MallProduct, pid).stock == 3
        assert (
            db.query(MallExchange).filter_by(user_id=uid, product_id=pid).count() == 0
        )
    r = client.get("/api/credit/balance", headers=h)
    assert r.json()["data"]["balance"] == 50


def test_exchange_invalid_products(client):
    """下架/不存在/库存 0 → 40916。"""
    pid_off = _make_product(name="下架品", enabled=0)
    pid_zero = _make_product(name="售罄品", stock=0)
    h, _ = _register(client)

    for pid in (pid_off, pid_zero, 99999):
        r = client.post("/api/mall/exchange", json={"product_id": pid}, headers=h)
        assert r.json()["code"] == 40916


def test_products_public_and_auth_required(client):
    """商品列表免登录；兑换/记录需登录（401）。"""
    pid = _make_product(name="公开商品")
    r = client.get("/api/mall/products")
    assert r.json()["code"] == 0
    names = [i["name"] for i in r.json()["data"]["items"]]
    assert "公开商品" in names

    assert client.post("/api/mall/exchange", json={"product_id": pid}).status_code == 401
    assert client.get("/api/mall/exchanges").status_code == 401


def test_products_pagination(client):
    """商品分页（id 正序）。"""
    ids = [_make_product(name=f"分页商品{i}") for i in range(3)]
    r = client.get("/api/mall/products?page=1&page_size=2")
    data = r.json()["data"]
    assert data["total"] >= 3
    got = [i["id"] for i in data["items"]]
    assert all(got[i] < got[i + 1] for i in range(len(got) - 1))  # 正序
