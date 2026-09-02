"""广场三 Tab（技术细节文档 §5.2 接口 13 / §6.3 推荐分公式）。

- latest：id 倒序（即最新发布在前）
- unsolved：status=0，推荐分倒序（悬赏加权让待解决帖获得曝光）
- recommend：全量帖，推荐分倒序
- score = heat + reward/10 - decay
  heat = answer_count×3 + like_count×2 + view_count×0.1
  decay = 待解决且发布超 DECAY_DAYS 天 → 50，否则 0
- 权重参数优先读 app_config（feed.*），缺省回落 settings/env
"""

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import AppConfig, Post
from app.modules.post.service import _card


def _cfg(db: Session, key: str, default: float) -> float:
    """app_config > 默认值（与 credit._cap 同模式，复用当前会话避免 StaticPool 回滚坑）。"""
    row = db.get(AppConfig, key)
    try:
        return float(row.value) if row is not None else default
    except (TypeError, ValueError):
        return default


def _score(db: Session, post: Post, now: datetime) -> float:
    w_ans = _cfg(db, "feed.weight_answer", 3.0)
    w_like = _cfg(db, "feed.weight_like", 2.0)
    w_view = _cfg(db, "feed.weight_view", 0.1)
    reward_div = _cfg(db, "feed.reward_divisor", 10.0)
    decay_days = _cfg(db, "feed.decay_days", float(settings.DECAY_DAYS))
    decay_penalty = _cfg(db, "feed.decay_penalty", 50.0)
    heat = post.answer_count * w_ans + post.like_count * w_like + post.view_count * w_view
    reward_weight = post.reward / reward_div
    decay = (
        decay_penalty
        if post.status == 0 and post.created_at < now - timedelta(days=decay_days)
        else 0.0
    )
    return heat + reward_weight - decay


def list_feed(db: Session, tab: str, offset: int, limit: int) -> dict:
    """广场列表：三 Tab。P0 数据量小，全量取回后内存排序分页。"""
    now = datetime.now()
    rows = (
        db.execute(select(Post).where(Post.deleted_at.is_(None)).order_by(Post.id.desc()))
        .scalars()
        .all()
    )
    if tab == "unsolved":
        rows = [p for p in rows if p.status == 0]
        rows.sort(key=lambda p: (_score(db, p, now), p.id), reverse=True)
    elif tab == "recommend":
        rows.sort(key=lambda p: (_score(db, p, now), p.id), reverse=True)
    # latest：已按 id 倒序
    return {
        "total": len(rows),
        "items": [_card(db, p) for p in rows[offset : offset + limit]],
    }
