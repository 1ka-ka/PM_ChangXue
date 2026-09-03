"""积分并发演练（V1.9，S12 遗留硬约束）：MySQL 真机 FOR UPDATE 行锁验证。

前置：DATABASE_URL 指向 MySQL 演练库且已 alembic upgrade head。
用法：DATABASE_URL=mysql+pymysql://... python -m scripts.concurrency_drill

验证四件事：
  1. 并发 grant/deduct 无丢失更新（终余额 = 初值 + 净变动）
  2. 流水 balance_after 连续（前一条 balance_after + change == 后一条）
  3. 余额不足 40902 并发下不产生负余额
  4. 商城限量商品并发兑换不超卖（成功数 == 初始库存，stock 归 0）
"""

import random
import threading
import time
import uuid

from sqlalchemy import select

from app.core.database import SessionLocal, engine
from app.models import CreditAccount, MallExchange, MallProduct, User
from app.modules.credit import service as credit
from app.modules.credit.sources import CreditSource
from app.modules.mall import service as mall

# 演练参数
WORKERS = 8          # 并发线程数
OPS_PER_WORKER = 25  # 每线程积分操作数
INITIAL_BALANCE = 10_000
OVERSELL_THREADS = 20  # 超卖演练线程数
PRODUCT_STOCK = 10

errors: list[str] = []


def _check(cond: bool, msg: str) -> None:
    tag = "PASS" if cond else "FAIL"
    print(f"  {tag}  {msg}")
    if not cond:
        errors.append(msg)


_phone_seq = 0


def _drill_phone() -> str:
    """演练专用手机号：时间戳+自增，跨次运行不撞唯一键。"""
    global _phone_seq
    _phone_seq += 1
    return f"138{int(time.time() * 1000) % 10 ** 8:08d}{_phone_seq % 10}"


def _make_user(phone: str | None = None) -> int:
    with SessionLocal() as db:
        u = User(phone=phone or _drill_phone(), password_hash="x", nickname="并发演练")
        db.add(u)
        db.flush()
        db.add(CreditAccount(user_id=u.id, balance=INITIAL_BALANCE))
        db.commit()
        return u.id


def drill_credit_concurrency() -> None:
    """并发 grant/deduct：终余额与流水连续性校验。"""
    print(f"==> 1/3 积分并发（{WORKERS} 线程 × {OPS_PER_WORKER} 操作）")
    uid = _make_user()
    expected_delta = 0
    lock = threading.Lock()

    def worker(seed: int) -> None:
        nonlocal expected_delta
        rng = random.Random(seed)
        local = 0
        for _ in range(OPS_PER_WORKER):
            amount = rng.randint(1, 5)
            is_grant = rng.random() < 0.5
            with SessionLocal() as db:
                try:
                    if is_grant:
                        credit.grant(db, uid, CreditSource.TASK, amount,
                                     apply_daily_cap=False, note="并发演练")
                    else:
                        credit.deduct(db, uid, CreditSource.REWARD, amount, note="并发演练")
                    db.commit()
                    local += amount if is_grant else -amount
                except Exception as e:  # noqa: BLE001
                    with lock:
                        errors.append(f"积分操作异常: {e}")
        with lock:
            expected_delta += local

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(WORKERS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    with SessionLocal() as db:
        balance = db.execute(
            select(CreditAccount.balance).where(CreditAccount.user_id == uid)
        ).scalar_one()
        from app.models import CreditLog
        rows = db.execute(
            select(CreditLog).where(CreditLog.user_id == uid).order_by(CreditLog.id)
        ).scalars().all()

    _check(balance == INITIAL_BALANCE + expected_delta,
           f"终余额无丢失更新（{balance} == {INITIAL_BALANCE} + ({expected_delta})）")
    _check(len(rows) == WORKERS * OPS_PER_WORKER + 0,
           f"流水条数齐全（{len(rows)} == {WORKERS * OPS_PER_WORKER}）")
    continuity = all(
        rows[i].balance_after + rows[i + 1].change == rows[i + 1].balance_after
        for i in range(len(rows) - 1)
    )
    _check(continuity and rows[0].balance_after - rows[0].change == INITIAL_BALANCE,
           "流水 balance_after 链连续（前余额+变动==后余额）")
    _check(all(r.balance_after >= 0 for r in rows), "全程无负余额")


def drill_insufficient_balance() -> None:
    """余额不足 40902：并发扣款不穿透为负。"""
    print("==> 2/3 余额不足并发拦截")
    uid = _make_user()
    with SessionLocal() as db:  # 清零余额后再并发扣款
        db.get(CreditAccount, uid).balance = 0
        db.commit()
    rejected = 0
    lock = threading.Lock()

    def worker() -> None:
        nonlocal rejected
        with SessionLocal() as db:
            try:
                credit.deduct(db, uid, CreditSource.SHOP, 100, note="超额演练")
                db.commit()
            except Exception:  # noqa: BLE001  40902 预期被拒
                with lock:
                    rejected += 1

    threads = [threading.Thread(target=worker) for _ in range(WORKERS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    with SessionLocal() as db:
        balance = db.execute(
            select(CreditAccount.balance).where(CreditAccount.user_id == uid)
        ).scalar_one()
    _check(balance == 0, f"余额保持 0 未穿透为负（实际 {balance}）")
    _check(rejected == WORKERS, f"{WORKERS} 笔超额扣款全部被拒（{rejected}）")


def drill_mall_oversell() -> None:
    """限量商品并发兑换：FOR UPDATE 防超卖。"""
    print(f"==> 3/3 商城超卖演练（{OVERSELL_THREADS} 线程抢 {PRODUCT_STOCK} 件）")
    with SessionLocal() as db:
        p = MallProduct(name=f"超卖演练{uuid.uuid4().hex[:6]}", description="drill",
                        price=1, stock=PRODUCT_STOCK, type=2, enabled=1)
        db.add(p)
        db.commit()
        pid = p.id

    uids = [_make_user() for _ in range(OVERSELL_THREADS)]
    success = 0
    oos = 0
    lock = threading.Lock()

    def worker(uid: int) -> None:
        nonlocal success, oos
        with SessionLocal() as db:
            user = db.get(User, uid)
            try:
                mall.exchange(db, user, pid)
                with lock:
                    success += 1
            except Exception as e:  # noqa: BLE001
                if "40916" in str(e) or "库存" in str(e):
                    with lock:
                        oos += 1
                else:
                    with lock:
                        errors.append(f"兑换异常: {e}")

    threads = [threading.Thread(target=worker, args=(u,)) for u in uids]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    with SessionLocal() as db:
        product = db.get(MallProduct, pid)
        exchanges = db.execute(
            select(MallExchange).where(MallExchange.product_id == pid)
        ).scalars().all()
    _check(success == PRODUCT_STOCK, f"成功兑换数 == 库存（{success}/{PRODUCT_STOCK}）")
    _check(product.stock == 0, f"库存归 0（实际 {product.stock}）")
    _check(len(exchanges) == PRODUCT_STOCK, f"兑换记录数 == 库存（{len(exchanges)}）")


def main() -> None:
    assert engine.dialect.name == "mysql", "本演练必须跑在 MySQL 上（SQLite 单写者无意义）"
    t0 = time.time()
    drill_credit_concurrency()
    drill_insufficient_balance()
    drill_mall_oversell()
    print(f"\n结果：{'全部通过' if not errors else '存在失败项'}"
          f"（{len(errors)} 失败 / 耗时 {time.time() - t0:.1f}s）")
    for e in errors:
        print(f"  FAIL  {e}")
    raise SystemExit(1 if errors else 0)


if __name__ == "__main__":
    main()
