"""管理后台：举报队列/处置四动作/标签管理/操作日志/最简看板（技术细节文档 §5.11 接口 31-38）。

处置动作（接口 32-35，统一入口 /admin/reports/{id}/action）：
- delete：级联软删被举报内容 + 相关通知 invalid
- ban：封禁内容作者（ban_days 1/7/0=永久）
- recall_credit：追回作者积分（recall 钳制至 0，流水记实际值）
- dismiss：驳回
全部动作写 admin_action_log 留痕；举报已处理 → 40911。

实现偏差（P0）：管理员删内容不回退帖子 status / 知识库条目（治理动作不改变状态机历史）。
"""

from datetime import datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import BizError, ErrCode
from app.models import (
    AdminActionLog,
    Answer,
    Comment,
    Post,
    Report,
    Tag,
    User,
)
from app.modules.account.service import brief
from app.modules.credit import service as credit_service
from app.modules.credit.sources import CreditSource
from app.modules.moderation.service import load_target
from app.modules.notify import service as notify_service

# admin_action_log.action 枚举（§3.4）
ACTION_DELETE_POST, ACTION_DELETE_ANSWER, ACTION_DELETE_COMMENT = 1, 2, 3
ACTION_BAN, ACTION_UNBAN, ACTION_RECALL, ACTION_DISMISS, ACTION_RESTORE = 4, 5, 6, 7, 8

_TARGET_ACTION = {1: ACTION_DELETE_POST, 2: ACTION_DELETE_ANSWER, 3: ACTION_DELETE_COMMENT}


def _log(db: Session, admin_id: int, action: int, reason: str, target_type=None, target_id=None):
    db.add(
        AdminActionLog(
            admin_id=admin_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            reason=reason,
        )
    )


def _snapshot(db: Session, target_type: int, target_id: int) -> dict:
    """被举报内容快照（已删也返回，供后台追溯）。"""
    if target_type == 1:
        p = db.get(Post, target_id)
        if p is None:
            return {"kind": "post", "deleted": True}
        return {
            "kind": "post", "deleted": p.deleted_at is not None,
            "title": p.title, "excerpt": (p.content or "")[:100],
        }
    if target_type == 2:
        a = db.get(Answer, target_id)
        if a is None:
            return {"kind": "answer", "deleted": True}
        return {
            "kind": "answer", "deleted": a.deleted_at is not None,
            "excerpt": a.content[:100], "post_id": a.post_id,
        }
    c = db.get(Comment, target_id)
    if c is None:
        return {"kind": "comment", "deleted": True}
    return {"kind": "comment", "deleted": c.deleted_at is not None, "excerpt": c.content[:100]}


def list_reports(db: Session, status: int | None, offset: int, limit: int) -> dict:
    """举报队列：report + 内容快照 + 作者 + 举报次数（同目标累计）。"""
    q = select(Report).order_by(Report.id.desc())
    if status is not None:
        q = q.where(Report.status == status)
    rows = db.execute(q).scalars().all()
    items = []
    for r in rows:
        report_count = len(
            db.execute(
                select(Report.id).where(
                    Report.target_type == r.target_type, Report.target_id == r.target_id
                )
            )
            .scalars()
            .all()
        )
        author_id = None
        target = None
        try:
            target, author_id = load_target(db, r.target_type, r.target_id)
        except BizError:
            pass  # 已删内容仍展示快照
        items.append(
            {
                "id": r.id,
                "reporter": brief(db.get(User, r.reporter_id)),
                "target_type": r.target_type,
                "target_id": r.target_id,
                "content": _snapshot(db, r.target_type, r.target_id),
                "author": brief(db.get(User, author_id)) if author_id else None,
                "reason": r.reason,
                "detail": r.detail,
                "status": r.status,
                "report_count": report_count,
                "created_at": r.created_at,
            }
        )
    return {"total": len(items), "items": items[offset : offset + limit]}


def _soft_delete_cascade(db: Session, target_type: int, target_id: int) -> None:
    """级联软删：帖→其下回答与全部评论；回答→其评论；评论→其回复。通知同步 invalid。"""
    now = datetime.now()
    if target_type == 1:
        post = db.get(Post, target_id)
        post.deleted_at = now
        answers = (
            db.execute(select(Answer).where(Answer.post_id == target_id, Answer.deleted_at.is_(None)))
            .scalars()
            .all()
        )
        for a in answers:
            a.deleted_at = now
            notify_service.invalidate(db, 2, a.id)
            _soft_delete_comments_of(db, 2, a.id, now)
        _soft_delete_comments_of(db, 1, target_id, now)
        notify_service.invalidate(db, 1, target_id)
    elif target_type == 2:
        a = db.get(Answer, target_id)
        a.deleted_at = now
        post = db.get(Post, a.post_id)
        if post is not None and post.answer_count > 0:
            post.answer_count -= 1
        _soft_delete_comments_of(db, 2, target_id, now)
        notify_service.invalidate(db, 2, target_id)
    else:
        _soft_delete_comments_of(db, 3, target_id, now, root_only=False)
        notify_service.invalidate(db, 3, target_id)


def _soft_delete_comments_of(db: Session, target_type: int, target_id: int, now: datetime) -> None:
    """软删挂接在目标上的评论（含根评论的级联回复）。"""
    roots = (
        db.execute(
            select(Comment).where(
                Comment.target_type == target_type,
                Comment.target_id == target_id,
                Comment.deleted_at.is_(None),
            )
        )
        .scalars()
        .all()
    )
    for c in roots:
        c.deleted_at = now
        notify_service.invalidate(db, 3, c.id)
        replies = (
            db.execute(
                select(Comment).where(Comment.parent_id == c.id, Comment.deleted_at.is_(None))
            )
            .scalars()
            .all()
        )
        for r in replies:
            r.deleted_at = now
            notify_service.invalidate(db, 3, r.id)


def act(
    db: Session,
    admin: User,
    report_id: int,
    action: str,
    reason: str,
    ban_days: int | None = None,
    amount: int | None = None,
) -> None:
    """处置举报：四动作统一入口。"""
    report = db.get(Report, report_id)
    if report is None:
        raise BizError(ErrCode.NOT_FOUND, "举报不存在")
    if report.status != 0:
        raise BizError(ErrCode.REPORT_HANDLED, "该举报已被处理")

    # 目标作者（内容可能已被作者删除——仍可封号/追回，删除动作直接视为完成）
    author_id = None
    try:
        _, author_id = load_target(db, report.target_type, report.target_id)
    except BizError:
        if action == "delete":
            author_id = None  # 内容已不存在，删除动作幂等完成

    if action == "delete":
        if author_id is not None:
            _soft_delete_cascade(db, report.target_type, report.target_id)
            _log(db, admin.id, _TARGET_ACTION[report.target_type], reason,
                 report.target_type, report.target_id)
        report.status = 1
    elif action == "ban":
        if author_id is None:
            raise BizError(ErrCode.NOT_FOUND, "被举报内容已删除，无法定位作者")
        if ban_days not in (0, 1, 7):
            raise BizError(ErrCode.BAD_REQUEST, "ban_days 须为 1/7/0(永久)")
        u = db.get(User, author_id)
        u.status = 1
        u.banned_until = None if ban_days == 0 else datetime.now() + timedelta(days=ban_days)
        _log(db, admin.id, ACTION_BAN, reason, 0, author_id)
        report.status = 1
    elif action == "recall_credit":
        if author_id is None:
            raise BizError(ErrCode.NOT_FOUND, "被举报内容已删除，无法定位作者")
        if not amount or amount <= 0:
            raise BizError(ErrCode.BAD_REQUEST, "追回积分须为正整数")
        actual = credit_service.recall(
            db, author_id, amount,
            ref_type=report.target_type, ref_id=report.target_id,
            note=f"管理员追回（举报 {report_id}）",
        )
        _log(db, admin.id, ACTION_RECALL, f"{reason}（实际追回 {actual}）",
             report.target_type, report.target_id)
        report.status = 1
    elif action == "dismiss":
        _log(db, admin.id, ACTION_DISMISS, reason, report.target_type, report.target_id)
        report.status = 2
    else:
        raise BizError(ErrCode.BAD_REQUEST, "无效处置动作")

    report.handled_by = admin.id
    report.result = reason
    db.commit()


# ---- 标签管理（接口 36）----


def list_tags(db: Session) -> list[dict]:
    rows = db.execute(select(Tag).order_by(Tag.sort, Tag.id)).scalars().all()
    return [{"id": t.id, "name": t.name, "sort": t.sort, "enabled": bool(t.enabled)} for t in rows]


def create_tag(db: Session, name: str, sort: int) -> dict:
    exists = db.execute(select(Tag.id).where(Tag.name == name)).scalar()
    if exists:
        raise BizError(ErrCode.BAD_REQUEST, "标签名已存在")
    t = Tag(name=name, sort=sort)
    db.add(t)
    db.commit()
    return {"id": t.id, "name": t.name, "sort": t.sort, "enabled": True}


def update_tag(db: Session, tag_id: int, name: str | None, sort: int | None, enabled: int | None) -> dict:
    t = db.get(Tag, tag_id)
    if t is None:
        raise BizError(ErrCode.NOT_FOUND, "标签不存在")
    if name is not None:
        dup = db.execute(select(Tag.id).where(Tag.name == name, Tag.id != tag_id)).scalar()
        if dup:
            raise BizError(ErrCode.BAD_REQUEST, "标签名已存在")
        t.name = name
    if sort is not None:
        t.sort = sort
    if enabled is not None:
        t.enabled = enabled
    db.commit()
    return {"id": t.id, "name": t.name, "sort": t.sort, "enabled": bool(t.enabled)}


# ---- 操作日志（接口 37）----


def list_logs(db: Session, admin_id: int | None, action: int | None, offset: int, limit: int) -> dict:
    q = select(AdminActionLog).order_by(AdminActionLog.id.desc())
    if admin_id is not None:
        q = q.where(AdminActionLog.admin_id == admin_id)
    if action is not None:
        q = q.where(AdminActionLog.action == action)
    rows = db.execute(q).scalars().all()
    return {
        "total": len(rows),
        "items": [
            {
                "id": l.id,
                "admin_id": l.admin_id,
                "admin_nickname": (db.get(User, l.admin_id).nickname if db.get(User, l.admin_id) else None),
                "action": l.action,
                "target_type": l.target_type,
                "target_id": l.target_id,
                "reason": l.reason,
                "created_at": l.created_at,
            }
            for l in rows[offset : offset + limit]
        ],
    }


# ---- 数据看板（接口 38）----


def stats(db: Session) -> dict:
    today_start = datetime.combine(datetime.now().date(), time.min)
    pending = len(
        db.execute(select(Report.id).where(Report.status == 0)).scalars().all()
    )
    dau = len(
        db.execute(select(User.id).where(User.last_login_at >= today_start)).scalars().all()
    )
    daily_posts = len(
        db.execute(select(Post.id).where(Post.created_at >= today_start)).scalars().all()
    )
    daily_accepts = len(
        db.execute(select(Post.id).where(Post.accepted_at >= today_start)).scalars().all()
    )
    return {
        "pending_reports": pending,
        "dau": dau,
        "daily_posts": daily_posts,
        "daily_accepts": daily_accepts,
    }
