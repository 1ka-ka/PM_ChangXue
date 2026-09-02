"""AI 无人值守兜底定时任务（V1.5）。

- 每 AI_FALLBACK_SCAN_INTERVAL 分钟扫描：无人回答超过 AI_FALLBACK_MINUTES 的帖子
- 人答优先：扫描时已有回答的帖跳过；已生成过 AI 参考回答的帖不重复生成
- 每轮最多 AI_FALLBACK_BATCH 条（防 LLM 过载）；单帖失败静默，下轮重试
- LLM 关闭 / 兜底关闭时任务直接返回；测试环境不注册调度
"""

import logging
from datetime import datetime, timedelta

from sqlalchemy import select

from app.core.config import settings
from app.core.database import SessionLocal
from app.models import Post

logger = logging.getLogger("changxue.ai_fallback")


def run_ai_fallback() -> None:
    """扫描一轮无人回答的超时帖，逐帖生成 AI 参考回答（独立会话，失败静默）。"""
    if not settings.LLM_ENABLED or not settings.AI_FALLBACK_ENABLED:
        return

    from app.gateway.client import LLMDegradedError, gateway
    from app.modules.post.service import _tags_of

    cutoff = datetime.now() - timedelta(minutes=settings.AI_FALLBACK_MINUTES)
    with SessionLocal() as db:  # 先取候选 id，逐帖独立会话避免长事务
        ids = (
            db.execute(
                select(Post.id)
                .where(
                    Post.deleted_at.is_(None),
                    Post.answer_count == 0,
                    Post.ai_answer.is_(None),
                    Post.created_at <= cutoff,
                )
                .order_by(Post.created_at)  # 最老的优先
                .limit(settings.AI_FALLBACK_BATCH)
            )
            .scalars()
            .all()
        )
    if not ids:
        return

    done = 0
    for pid in ids:
        try:
            with SessionLocal() as db:
                post = db.get(Post, pid)
                if (
                    post is None
                    or post.deleted_at is not None
                    or post.ai_answer
                    or post.answer_count > 0  # 重验：扫描窗口内可能已有人答
                ):
                    continue
                out = gateway.invoke(
                    "ref_answer",
                    {
                        "post_id": post.id,
                        "title": post.title,
                        "content": (post.content or "")[:2000],
                        "tag_names": [t.name for t in _tags_of(db, post.id)],
                    },
                )
                post.ai_answer = out["answer_text"]
                post.ai_answer_at = datetime.now()
                db.commit()
                done += 1
        except LLMDegradedError:
            continue  # 单帖降级：下轮扫描重试
        except Exception:
            logger.exception("AI 兜底生成异常 post_id=%s", pid)
    if done:
        logger.info("AI 兜底完成 本轮生成 %s 条（候选 %s）", done, len(ids))


def register(scheduler) -> None:
    """注册到调度器（main lifespan 调用；测试环境不注册）。"""
    scheduler.add_job(
        run_ai_fallback,
        "interval",
        minutes=settings.AI_FALLBACK_SCAN_INTERVAL,
        id="ai_fallback",
    )
