"""credit 路由：接口 4（每日登录）、28（明细）、29（余额）。"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import PageParams, get_current_user
from app.core.response import ok
from app.models import CreditLog, User
from app.modules.credit import service
from app.modules.credit.sources import CreditSource, SOURCE_TEXT

router = APIRouter()


@router.post("/credit/daily-login")
def daily_login(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """每日登录积分：幂等（当日已领返回 granted=0）。"""
    if service.has_daily_login_today(db, user.id):
        return ok({"granted": 0, "reason": "今日已领取"})
    granted = service.grant(
        db,
        user.id,
        CreditSource.DAILY_LOGIN,
        _login_amount(db),
        note="每日登录",
    )
    db.commit()
    return ok({"granted": granted} if granted > 0 else {"granted": 0, "reason": "今日已达封顶"})


def _login_amount(db: Session) -> int:
    """登录分值：app_config > settings（同会话查询，避免嵌套 Session 破坏事务）。"""
    from app.core.config import settings
    from app.models import AppConfig

    row = db.get(AppConfig, "credit.daily_login")
    return int(row.value) if row is not None else settings.CREDIT_DAILY_LOGIN


@router.get("/credit/logs")
def credit_logs(
    page: PageParams = Depends(),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """积分明细：分页，按时间倒序，source_text 附加文案。"""
    total = db.execute(
        select(CreditLog).where(CreditLog.user_id == user.id)
    ).scalars().all()
    rows = db.execute(
        select(CreditLog)
        .where(CreditLog.user_id == user.id)
        .order_by(CreditLog.id.desc())
        .offset(page.offset)
        .limit(page.limit)
    ).scalars().all()
    return ok(
        {
            "total": len(total),
            "items": [
                {
                    "id": r.id,
                    "change": r.change,
                    "balance_after": r.balance_after,
                    "source": r.source,
                    "source_text": SOURCE_TEXT.get(r.source, str(r.source)),
                    "ref_id": r.ref_id,
                    "note": r.note,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in rows
            ],
        }
    )


@router.get("/credit/balance")
def credit_balance(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok({"balance": service.get_balance(db, user.id)})
