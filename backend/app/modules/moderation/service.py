"""举报业务：提交（40903 去重）+ 目标校验（技术细节文档 §5.10 接口 30）。"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import BizError, ErrCode
from app.core.sensitive import contains_sensitive
from app.models import Answer, Comment, Post, Report, User


def load_target(db: Session, target_type: int, target_id: int):
    """举报/处置目标存在性校验：1 帖子 / 2 回答 / 3 评论；返回 (对象, 作者id)。"""
    if target_type == 1:
        p = db.get(Post, target_id)
        if p is None or p.deleted_at is not None:
            raise BizError(ErrCode.NOT_FOUND, "帖子不存在或已删除")
        return p, p.author_id
    if target_type == 2:
        a = db.get(Answer, target_id)
        if a is None or a.deleted_at is not None:
            raise BizError(ErrCode.NOT_FOUND, "回答不存在或已删除")
        return a, a.author_id
    if target_type == 3:
        c = db.get(Comment, target_id)
        if c is None or c.deleted_at is not None:
            raise BizError(ErrCode.NOT_FOUND, "评论不存在或已删除")
        return c, c.author_id
    raise BizError(ErrCode.BAD_REQUEST, "目标类型无效")


def create_report(
    db: Session, user: User, target_type: int, target_id: int, reason: int, detail: str
) -> None:
    """提交举报：目标须存在（40002）；同一用户对同一目标仅一次（40903）。"""
    load_target(db, target_type, target_id)
    if contains_sensitive(detail):
        raise BizError(ErrCode.SENSITIVE_WORD, "举报说明含违禁词")
    dup = db.execute(
        select(Report.id).where(
            Report.reporter_id == user.id,
            Report.target_type == target_type,
            Report.target_id == target_id,
        )
    ).scalar()
    if dup:
        raise BizError(ErrCode.DUPLICATE_ACTION, "已举报过该内容，请等待处理")
    report = Report(
        reporter_id=user.id,
        target_type=target_type,
        target_id=target_id,
        reason=reason,
        detail=detail,
    )
    db.add(report)
    db.commit()
    return report.id


# ---- AI 违规分级（V1.3 moderation 场景）----


def moderate_report_task(report_id: int) -> None:
    """BackgroundTasks 入口：异步为被举报内容生成 AI 违规分级，辅助管理员分诊；失败静默。"""
    from app.core.database import SessionLocal
    from app.gateway.client import LLMDegradedError, gateway

    with SessionLocal() as db:
        r = db.get(Report, report_id)
        if r is None:
            return
        try:
            target, _ = load_target(db, r.target_type, r.target_id)
        except BizError:
            return  # 内容已删，无需分级
        if r.target_type == 1:
            content = f"{target.title} {target.content or ''}"
        else:
            content = target.content or ""
        try:
            out = gateway.invoke("moderation", {"content": content[:2000]})
        except LLMDegradedError:
            return
        r = db.get(Report, report_id)
        if r is not None:
            r.ai_level = out["level"]
            r.ai_violation_type = out.get("violation_type")
            db.commit()
