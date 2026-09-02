"""助人榜：结算 gratitude_stat → rank_snapshot + 榜单查询（技术细节文档 §5.7 接口 24）。

- 榜单公布以快照为准（防历史数据变动）
- 查询当前期无快照（未结算）→ 返回上期快照 + settling: true
- 周期键格式与 gratitude_stat 一致：周 2026-W36 / 月 2026-09
"""

from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import GratitudeStat, RankSnapshot, User
from app.modules.account.service import brief


def week_key(dt: datetime) -> str:
    iso = dt.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def month_key(dt: datetime) -> str:
    return dt.strftime("%Y-%m")


def prev_keys(now: datetime | None = None) -> dict[int, str]:
    """刚刚结束的周/月周期键：{1: 上周键, 2: 上月键}。"""
    now = now or datetime.now()
    return {1: week_key(now - timedelta(days=7)), 2: month_key(now.replace(day=1) - timedelta(days=1))}


def settle(db: Session, period_type: int, period_key: str) -> int:
    """结算指定周期：TOP N 写入 rank_snapshot（幂等：先清后写）。返回写入行数。"""
    rows = (
        db.execute(
            select(GratitudeStat)
            .where(GratitudeStat.period_type == period_type, GratitudeStat.period_key == period_key)
            .order_by(GratitudeStat.value.desc(), GratitudeStat.user_id)
        )
        .scalars()
        .all()
    )
    db.execute(
        delete(RankSnapshot).where(
            RankSnapshot.period_type == period_type, RankSnapshot.period_key == period_key
        )
    )
    for rank, row in enumerate(rows[: settings.RANK_TOP_N], start=1):
        db.add(
            RankSnapshot(
                period_type=period_type,
                period_key=period_key,
                rank=rank,
                user_id=row.user_id,
                value=row.value,
            )
        )
    db.commit()
    return min(len(rows), settings.RANK_TOP_N)


def list_ranks(db: Session, period: str) -> dict:
    """榜单查询：week/month → period_type 1/2；当期未结算回落上期 + settling。"""
    period_type = 1 if period == "week" else 2
    now = datetime.now()
    current = week_key(now) if period_type == 1 else month_key(now)
    prev = prev_keys(now)[period_type]

    key, settling = current, False
    if not _has_snapshot(db, period_type, current):
        key, settling = prev, True
    rows = (
        db.execute(
            select(RankSnapshot)
            .where(RankSnapshot.period_type == period_type, RankSnapshot.period_key == key)
            .order_by(RankSnapshot.rank)
        )
        .scalars()
        .all()
    )
    return {
        "period": key,
        "settling": settling,
        "items": [
            {"rank": r.rank, "user": brief(db.get(User, r.user_id)), "value": r.value}
            for r in rows
        ],
    }


def _has_snapshot(db: Session, period_type: int, period_key: str) -> bool:
    return (
        db.execute(
            select(RankSnapshot.id)
            .where(
                RankSnapshot.period_type == period_type, RankSnapshot.period_key == period_key
            )
            .limit(1)
        ).scalar()
        is not None
    )
