"""采纳状态机：单事务编排（技术细节文档 §6.1 采纳 8 步）。

accept 事务步骤：
1. 校验：仅提问者（40301）/ 采纳数 < 3（40901）/ 目标未删且未被采纳（40907）
2. answer.is_accepted = 1
3. 首次采纳：post.status = 1 + accepted_at + 创建 knowledge_item（存在则忽略）
4. credit.grant(+30)（受日封顶，感谢值不受影响）
5. gratitude 三周期（周/月/累计）各 +30
6. 通知回答者
set_best：目标须已被采纳（40908），先清后置，零账务变动。
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import BizError, ErrCode
from app.models import (
    Answer,
    GratitudeStat,
    KnowledgeItem,
    Notification,
    Post,
    User,
)
from app.modules.credit import service as credit_service
from app.modules.credit.sources import CreditSource


def _gratitude_keys() -> list[tuple[int, str]]:
    """当前周/月/累计三个周期键。"""
    now = datetime.now()
    iso = now.isocalendar()
    return [
        (1, f"{iso.year}-W{iso.week:02d}"),
        (2, now.strftime("%Y-%m")),
        (3, "ALL"),
    ]


def _add_gratitude(db: Session, user_id: int, amount: int) -> None:
    for period_type, period_key in _gratitude_keys():
        row = db.execute(
            select(GratitudeStat).where(
                GratitudeStat.user_id == user_id,
                GratitudeStat.period_type == period_type,
                GratitudeStat.period_key == period_key,
            )
        ).scalar_one_or_none()
        if row is None:
            db.add(
                GratitudeStat(
                    user_id=user_id, period_type=period_type, period_key=period_key, value=amount
                )
            )
        else:
            row.value += amount


def accept(db: Session, user: User, answer_id: int) -> dict:
    """采纳回答：单事务 8 步编排。"""
    answer = db.get(Answer, answer_id)
    if answer is None or answer.deleted_at is not None:
        raise BizError(ErrCode.NOT_FOUND, "回答不存在或已删除")
    post = db.get(Post, answer.post_id)
    if post is None or post.deleted_at is not None:
        raise BizError(ErrCode.NOT_FOUND, "帖子不存在或已删除")
    if post.author_id != user.id:
        raise BizError(ErrCode.FORBIDDEN, "仅提问者可采纳回答")
    if answer.is_accepted:
        raise BizError(ErrCode.ALREADY_ACCEPTED, "该回答已被采纳")
    accepted_count = (
        db.execute(
            select(Answer.id).where(
                Answer.post_id == post.id,
                Answer.is_accepted == 1,
                Answer.deleted_at.is_(None),
            )
        )
        .scalars()
        .all()
    )
    if len(accepted_count) >= settings.ACCEPT_MAX:
        raise BizError(ErrCode.ACCEPT_LIMIT, f"每帖最多采纳 {settings.ACCEPT_MAX} 个回答")

    # ---- 单事务编排 ----
    answer.is_accepted = 1
    first_accept = post.status == 0
    if first_accept:
        post.status = 1
        post.accepted_at = datetime.now()
        if db.get(KnowledgeItem, post.id) is None:
            db.add(KnowledgeItem(post_id=post.id))
    granted_credit = credit_service.grant(
        db,
        answer.author_id,
        CreditSource.ACCEPTED,
        settings.CREDIT_ACCEPT,
        ref_type=2,
        ref_id=answer.id,
        note=f"回答被采纳（帖子 {post.id}）",
    )
    _add_gratitude(db, answer.author_id, 30)
    db.add(
        Notification(
            user_id=answer.author_id,  # 接收者
            type=4,  # 被采纳
            actor_id=user.id,
            target_type=2,
            target_id=answer.id,
        )
    )
    db.commit()
    return {
        "post_status": post.status,
        "granted": {"credit": granted_credit, "gratitude": 30},
    }


def set_best(db: Session, user: User, answer_id: int) -> dict:
    """设置最佳答案：仅提问者；目标须已被采纳；先清后置；零账务变动。"""
    answer = db.get(Answer, answer_id)
    if answer is None or answer.deleted_at is not None:
        raise BizError(ErrCode.NOT_FOUND, "回答不存在或已删除")
    post = db.get(Post, answer.post_id)
    if post is None or post.deleted_at is not None:
        raise BizError(ErrCode.NOT_FOUND, "帖子不存在或已删除")
    if post.author_id != user.id:
        raise BizError(ErrCode.FORBIDDEN, "仅提问者可设置最佳答案")
    if not answer.is_accepted:
        raise BizError(ErrCode.TARGET_NOT_ACCEPTED, "仅已被采纳的回答可设为最佳")
    # 先清后置（每帖唯一最佳）
    others = (
        db.execute(
            select(Answer).where(
                Answer.post_id == post.id,
                Answer.is_best == 1,
                Answer.id != answer.id,
            )
        )
        .scalars()
        .all()
    )
    for o in others:
        o.is_best = 0
    answer.is_best = 1
    db.commit()
    return {"best_answer_id": answer.id}
