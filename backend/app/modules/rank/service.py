"""助人榜：结算 gratitude_stat → rank_snapshot + 榜单查询（技术细节文档 §5.7 接口 24）。

- 感谢值榜（gratitude）：周/月快照制——榜单公布以快照为准（防历史数据变动），
  查询当前期无快照（未结算）→ 返回上期快照 + settling: true
- 回答数/采纳数榜（answers/accepts，V1.14）：日/周/月当期实时榜——
  直接查 answer 表时间窗统计，进行中数据实时刷新（日榜只有在实时口径下才有意义）
- 周期键格式与 gratitude_stat 一致：日 2026-10-02 / 周 2026-W36 / 月 2026-09
"""

from datetime import datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Answer, GratitudeStat, RankSnapshot, User
from app.modules.account.service import brief


def week_key(dt: datetime) -> str:
    iso = dt.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def month_key(dt: datetime) -> str:
    return dt.strftime("%Y-%m")


def day_key(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


def window_start(period: str, now: datetime | None = None) -> datetime:
    """实时榜时间窗起点：日=今日 0 点 / 周=本周一 0 点 / 月=本月 1 日 0 点。"""
    now = now or datetime.now()
    if period == "day":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "week":
        monday = now.date() - timedelta(days=now.weekday())
        return datetime(monday.year, monday.month, monday.day)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


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


def list_live_ranks(db: Session, metric: str, period: str) -> dict:
    """回答数/采纳数当期实时榜（V1.14）：时间窗内按作者聚合 answer 表。

    - answers：created_at 落窗（回答发布时间计）
    - accepts：accepted_at 落窗（采纳发生时间计，与感谢值口径一致）
    - 排除已删除回答与已注销用户；并列时 user_id 升序（与快照结算一致）
    """
    now = datetime.now()
    start = window_start(period, now)
    cond = [Answer.deleted_at.is_(None), Answer.created_at >= start]
    if metric == "accepts":
        cond = [
            Answer.deleted_at.is_(None),
            Answer.is_accepted == 1,
            Answer.accepted_at >= start,
        ]
    rows = db.execute(
        select(Answer.author_id, func.count(Answer.id).label("cnt"))
        .where(*cond)
        .group_by(Answer.author_id)
    ).all()
    # 过滤不存在/已注销用户后排序取 TOP N（并列按 user_id 升序）
    users = {uid: db.get(User, uid) for uid, _ in rows}
    counts = [
        (uid, cnt)
        for uid, cnt in rows
        if users[uid] is not None and users[uid].deleted_at is None
    ]
    counts.sort(key=lambda x: (-x[1], x[0]))
    items = [
        {"rank": rank, "user": brief(users[uid]), "value": cnt}
        for rank, (uid, cnt) in enumerate(counts[: settings.RANK_TOP_N], start=1)
    ]
    if period == "day":
        key = day_key(now)
    elif period == "week":
        key = week_key(now)
    else:
        key = month_key(now)
    return {"period": key, "settling": False, "items": items}
