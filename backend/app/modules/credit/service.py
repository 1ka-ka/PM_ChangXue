"""CreditService：积分账务唯一入口（ARCH §7.1）。

规则：
- 所有分值变动必须经 grant/deduct，同库同事务
- grant 产出类受日封顶约束：当日累计已达封顶 → 记 0 分流水（note 标注封顶），不发放
- deduct 余额不足抛 40902（调用方整体回滚）
- 流水 balance_after 保证连续性
- 行锁：MySQL SELECT...FOR UPDATE；SQLite 单写者特性天然串行（S12 MySQL 演练补并发用例）
"""

from datetime import datetime, time, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import BizError, ErrCode
from app.models import CreditAccount, CreditLog
from app.modules.credit.sources import CreditSource


def _today_start() -> datetime:
    """当日 00:00（本地时区），日封顶统计窗口。"""
    now = datetime.now()
    return datetime.combine(now.date(), time.min)


def _lock_account(db: Session, user_id: int) -> CreditAccount:
    """锁定积分账户行；不存在则懒创建（余额 0）。"""
    if db.bind.dialect.name == "mysql":
        row = db.execute(
            select(CreditAccount).where(CreditAccount.user_id == user_id).with_for_update()
        ).scalar_one_or_none()
    else:
        row = db.execute(
            select(CreditAccount).where(CreditAccount.user_id == user_id)
        ).scalar_one_or_none()
    if row is None:
        row = CreditAccount(user_id=user_id, balance=0)
        db.add(row)
        db.flush()
    return row


def _today_income(db: Session, user_id: int) -> int:
    """当日产出类流水合计（封顶统计口径）。"""
    rows = db.execute(
        select(CreditLog.change).where(
            CreditLog.user_id == user_id,
            CreditLog.created_at >= _today_start(),
            CreditLog.change > 0,
        )
    ).scalars().all()
    return sum(rows)


def grant(
    db: Session,
    user_id: int,
    source: CreditSource,
    amount: int,
    *,
    ref_type: int | None = None,
    ref_id: int | None = None,
    note: str = "",
    apply_daily_cap: bool = True,
) -> int:
    """发放积分（产出类默认受日封顶约束）。

    返回实际发放值（0=被封顶拦截）。
    调用方负责 commit——本函数只做变更，不开事务边界。
    """
    if amount <= 0:
        raise ValueError("grant amount 必须为正")
    account = _lock_account(db, user_id)

    granted = amount
    if apply_daily_cap and source.is_income:
        cap_left = _cap(db) - _today_income(db, user_id)
        if cap_left <= 0:
            granted = 0
        else:
            granted = min(amount, cap_left)

    if granted > 0:
        account.balance += granted
    db.add(
        CreditLog(
            user_id=user_id,
            change=granted,
            balance_after=account.balance,
            source=source.value,
            ref_type=ref_type,
            ref_id=ref_id,
            note=note if granted > 0 else f"{note}｜日封顶未发放".lstrip("｜"),
        )
    )
    return granted


def deduct(
    db: Session,
    user_id: int,
    source: CreditSource,
    amount: int,
    *,
    ref_type: int | None = None,
    ref_id: int | None = None,
    note: str = "",
) -> None:
    """扣除积分：余额不足抛 40902（含当前余额），调用方整体回滚。"""
    if amount <= 0:
        raise ValueError("deduct amount 必须为正")
    account = _lock_account(db, user_id)
    if account.balance < amount:
        raise BizError(
            ErrCode.CREDIT_INSUFFICIENT,
            f"积分不足（当前 {account.balance}，需 {amount}）",
        )
    account.balance -= amount
    db.add(
        CreditLog(
            user_id=user_id,
            change=-amount,
            balance_after=account.balance,
            source=source.value,
            ref_type=ref_type,
            ref_id=ref_id,
            note=note,
        )
    )


def recall(
    db: Session,
    user_id: int,
    amount: int,
    *,
    ref_type: int | None = None,
    ref_id: int | None = None,
    note: str = "",
) -> int:
    """质量追回（管理员）：余额不足时追回至 0，流水记实际值（40912 语义）。"""
    account = _lock_account(db, user_id)
    actual = min(amount, account.balance)
    account.balance -= actual
    db.add(
        CreditLog(
            user_id=user_id,
            change=-actual,
            balance_after=account.balance,
            source=CreditSource.RECALL.value,
            ref_type=ref_type,
            ref_id=ref_id,
            note=note if actual == amount else f"{note}（余额不足，实际追回 {actual}）",
        )
    )
    return actual


def get_balance(db: Session, user_id: int) -> int:
    account = db.get(CreditAccount, user_id)
    return account.balance if account else 0


def has_daily_login_today(db: Session, user_id: int) -> bool:
    """当日是否已领取登录积分（幂等判定）。"""
    return (
        db.execute(
            select(CreditLog.id).where(
                CreditLog.user_id == user_id,
                CreditLog.source == CreditSource.DAILY_LOGIN.value,
                CreditLog.created_at >= _today_start(),
            ).limit(1)
        ).scalar()
        is not None
    )


def _cap(db: Session) -> int:
    """日封顶值：app_config > settings。

    注意：必须用当前 db 会话查询——appconfig.get_config 会开独立 Session，
    在共享连接上其 close() 的 ROLLBACK 会破坏外层未提交事务。
    """
    from app.core.config import settings
    from app.models import AppConfig

    row = db.get(AppConfig, "credit.daily_cap")
    return int(row.value) if row is not None else settings.CREDIT_DAILY_CAP
