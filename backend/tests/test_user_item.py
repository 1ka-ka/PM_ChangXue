"""V1.15 个性化装扮测试：兑换入背包/重复持有 40917/佩戴卸下搭配/未持有 40918/
品类不匹配/brief 带 equipped/感谢值榜当期实时。"""

import pytest

from app.core.database import SessionLocal
from app.models import GratitudeStat, MallProduct
from app.modules.credit import service as credit_service
from app.modules.credit.sources import CreditSource

PASSWORD = "password123"
# 独立号段：137 前缀 4M-5M（test_dm 仅用 1M-2M，其余见 PROJECT_STATE 号段表）
_seq = iter(range(4_000_000, 5_000_000))


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
    """建测试商品（默认虚拟头衔 50 分不限量），登记待清理，返回 id。"""
    defaults = dict(
        name="测试头衔", description="单元测试专用", price=50,
        stock=-1, type=1, category=1, payload="测试官", enabled=1,
    )
    defaults.update(kw)
    with SessionLocal() as db:
        p = MallProduct(**defaults)
        db.add(p)
        db.commit()
        _created_ids.append(p.id)
        return p.id


def _top_up(uid: int, amount: int = 1000):
    with SessionLocal() as db:
        credit_service.grant(
            db, uid, CreditSource.TASK, amount, apply_daily_cap=False, note="测试充值"
        )
        db.commit()


def test_exchange_virtual_enters_inventory(client):
    """虚拟商品兑换即入背包，列表带 category/payload。"""
    pid = _make_product(name="徽章测试", category=2, payload="🏅")
    h, uid = _register(client)
    _top_up(uid, 100)

    r = client.post("/api/mall/exchange", json={"product_id": pid}, headers=h)
    assert r.json()["code"] == 0

    r = client.get("/api/account/items", headers=h)
    data = r.json()["data"]
    assert len(data["items"]) == 1
    item = data["items"][0]
    assert item["product_id"] == pid
    assert item["category"] == 2 and item["payload"] == "🏅"
    assert item["slot"] == "badge" and item["equipped"] is False
    assert data["equipped"] == {}


def test_exchange_duplicate_rejected(client):
    """重复兑换同款虚拟商品 → 40917，背包仍只有一件。"""
    pid = _make_product(name="重复头衔")
    h, uid = _register(client)
    _top_up(uid, 200)

    assert client.post("/api/mall/exchange", json={"product_id": pid}, headers=h).json()["code"] == 0
    r = client.post("/api/mall/exchange", json={"product_id": pid}, headers=h)
    assert r.json()["code"] == 40917

    r = client.get("/api/account/items", headers=h)
    assert len(r.json()["data"]["items"]) == 1


def test_equip_and_unequip(client):
    """佩戴 → brief/auth.me 带 equipped；卸下 → equipped 清空。"""
    pid = _make_product(name="佩戴头衔", payload="大侠")
    h, uid = _register(client)
    _top_up(uid, 100)
    client.post("/api/mall/exchange", json={"product_id": pid}, headers=h)

    # 佩戴
    r = client.put("/api/account/equip", json={"equips": {"title": pid}}, headers=h)
    assert r.json()["code"] == 0
    assert r.json()["data"]["equipped"]["title"]["payload"] == "大侠"

    # 背包标记已佩戴
    r = client.get("/api/account/items", headers=h)
    assert r.json()["data"]["items"][0]["equipped"] is True

    # brief 通道（auth/me）
    r = client.get("/api/auth/me", headers=h)
    assert r.json()["data"]["equipped"]["title"]["product_id"] == pid

    # 卸下
    r = client.put("/api/account/equip", json={"equips": {"title": None}}, headers=h)
    assert r.json()["code"] == 0 and r.json()["data"]["equipped"] == {}
    r = client.get("/api/auth/me", headers=h)
    assert r.json()["data"]["equipped"] is None


def test_equip_batch_and_mixed_slots(client):
    """批量搭配：一次佩戴头衔+徽章，互不影响。"""
    pid_t = _make_product(name="搭配头衔", payload="卷王")
    pid_b = _make_product(name="搭配徽章", category=2, payload="🔥")
    h, uid = _register(client)
    _top_up(uid, 200)
    client.post("/api/mall/exchange", json={"product_id": pid_t}, headers=h)
    client.post("/api/mall/exchange", json={"product_id": pid_b}, headers=h)

    r = client.put(
        "/api/account/equip",
        json={"equips": {"title": pid_t, "badge": pid_b}},
        headers=h,
    )
    equipped = r.json()["data"]["equipped"]
    assert equipped["title"]["payload"] == "卷王"
    assert equipped["badge"]["payload"] == "🔥"


def test_equip_not_owned_or_mismatched(client):
    """未持有佩戴 → 40918；品类不匹配 → 40001；未知槽位 → 40001。"""
    pid_t = _make_product(name="别人头衔", payload="X")
    pid_f = _make_product(name="金框", category=3, payload="gold")
    h, uid = _register(client)
    _top_up(uid, 200)
    client.post("/api/mall/exchange", json={"product_id": pid_f}, headers=h)

    # 未持有
    r = client.put("/api/account/equip", json={"equips": {"title": pid_t}}, headers=h)
    assert r.json()["code"] == 40918
    # 品类不匹配（拿头像框当头衔戴）
    r = client.put("/api/account/equip", json={"equips": {"title": pid_f}}, headers=h)
    assert r.json()["code"] == 40001
    # 未知槽位
    r = client.put("/api/account/equip", json={"equips": {"hat": pid_f}}, headers=h)
    assert r.json()["code"] == 40001
    # 空字典
    r = client.put("/api/account/equip", json={"equips": {}}, headers=h)
    assert r.json()["code"] == 40001


def test_public_profile_shows_equipped(client):
    """个人主页（公开视角）返回 equipped（brief 通道）。"""
    pid = _make_product(name="主页头衔", payload="热心大佬")
    h, uid = _register(client)
    _top_up(uid, 100)
    client.post("/api/mall/exchange", json={"product_id": pid}, headers=h)
    client.put("/api/account/equip", json={"equips": {"title": pid}}, headers=h)

    r = client.get(f"/api/account/users/{uid}")
    assert r.json()["data"]["equipped"]["title"]["payload"] == "热心大佬"


def test_equip_font_and_skin_slots(client):
    """V1.16 字体/皮肤槽位：category 6/7 商品可佩戴，equipped 快照带 payload 样式 key。"""
    pid_font = _make_product(name="楷体", category=6, payload="kai")
    pid_skin = _make_product(name="樱花皮肤", category=7, payload="sakura")
    h, uid = _register(client)
    _top_up(uid, 200)
    client.post("/api/mall/exchange", json={"product_id": pid_font}, headers=h)
    client.post("/api/mall/exchange", json={"product_id": pid_skin}, headers=h)

    r = client.put(
        "/api/account/equip",
        json={"equips": {"font": pid_font, "skin": pid_skin}},
        headers=h,
    )
    equipped = r.json()["data"]["equipped"]
    assert equipped["font"]["payload"] == "kai"
    assert equipped["skin"]["payload"] == "sakura"

    # 背包槽位归类正确
    r = client.get("/api/account/items", headers=h)
    by_slot = {i["slot"]: i for i in r.json()["data"]["items"]}
    assert by_slot["font"]["equipped"] is True
    assert by_slot["skin"]["equipped"] is True

    # 品类不匹配：拿字体商品当头衔戴 → 40001
    r = client.put("/api/account/equip", json={"equips": {"title": pid_font}}, headers=h)
    assert r.json()["code"] == 40001


def test_equip_pet_slot(client):
    """V1.17 宠物槽位：category 8 商品可佩戴，公开主页带宠物挂件数据。"""
    pid = _make_product(name="橘猫", category=8, payload="🐱")
    h, uid = _register(client)
    _top_up(uid, 100)
    client.post("/api/mall/exchange", json={"product_id": pid}, headers=h)

    r = client.put("/api/account/equip", json={"equips": {"pet": pid}}, headers=h)
    equipped = r.json()["data"]["equipped"]
    assert equipped["pet"]["payload"] == "🐱"

    # 公开主页（他人视角）携带宠物挂件
    r = client.get(f"/api/account/users/{uid}")
    assert r.json()["data"]["equipped"]["pet"]["payload"] == "🐱"


def test_gratitude_rank_current_period_realtime(client):
    """感谢值周榜当期实时：本周 gratitude_stat 直查即出，不再回落上期。"""
    h, uid = _register(client, "感谢值大户")
    with SessionLocal() as db:
        import datetime

        iso = datetime.datetime.now().isocalendar()
        week_key = f"{iso.year}-W{iso.week:02d}"
        db.add(
            GratitudeStat(
                user_id=uid, period_type=1, period_key=week_key, value=999
            )
        )
        db.commit()

    r = client.get("/api/ranks?metric=gratitude&period=week")
    data = r.json()["data"]
    assert data["settling"] is False
    assert data["items"], "当期实时榜不应为空"
    top = next((i for i in data["items"] if i["user"]["id"] == uid), None)
    assert top is not None and top["value"] == 999
    # brief 通道携带 equipped 字段
    assert "equipped" in top["user"]
