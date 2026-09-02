"""搜索：知识库优先 → 降级广场（技术细节文档 §5.6 接口 23，PRD M4-F14）。

流程：
1. 先查 knowledge_item JOIN post（标题模糊 + 标签筛选，过滤软删）→ 命中 source=kb
2. 未命中降级查广场帖（标题/内容模糊 + 标签筛选）→ source=plaza，
   写 search_degrade 埋点（关键词、广场结果数），响应附 degraded: true
3. 均无 → source=empty
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import BizError, ErrCode
from app.models import KnowledgeItem, Post, PostTag, TrackingEvent, User
from app.modules.post.service import _card


def _tag_filter(q, tag_id: int | None):
    if tag_id is None:
        return q
    return q.where(
        Post.id.in_(select(PostTag.post_id).where(PostTag.tag_id == tag_id))
    )


def search(
    db: Session, viewer: User | None, q: str | None, tag_id: int | None, offset: int, limit: int
) -> dict:
    if not q and tag_id is None:
        raise BizError(ErrCode.BAD_REQUEST, "关键词与标签至少提供一个")
    q = (q or "").strip()

    # ---- 1. 知识库优先（标题模糊 + 标签） ----
    kb_query = (
        select(Post)
        .join(KnowledgeItem, KnowledgeItem.post_id == Post.id)
        .where(Post.deleted_at.is_(None))
    )
    if q:
        kb_query = kb_query.where(Post.title.contains(q, autoescape=True))
    kb_query = _tag_filter(kb_query, tag_id)
    kb_rows = db.execute(kb_query.order_by(Post.id.desc())).scalars().all()

    if kb_rows:
        return {
            "source": "kb",
            "items": [_card(db, p) for p in kb_rows[offset : offset + limit]],
            "total": len(kb_rows),
        }

    # ---- 2. 降级广场（标题/内容模糊 + 标签） ----
    plaza_query = select(Post).where(Post.deleted_at.is_(None))
    if q:
        plaza_query = plaza_query.where(
            Post.title.contains(q, autoescape=True)
            | Post.content.contains(q, autoescape=True)
        )
    plaza_query = _tag_filter(plaza_query, tag_id)
    plaza_rows = db.execute(plaza_query.order_by(Post.id.desc())).scalars().all()

    if not plaza_rows:
        return {"source": "empty", "items": [], "total": 0}

    # 降级埋点：失败不影响业务（独立提交后继续；失败仅吞掉）
    db.add(
        TrackingEvent(
            user_id=viewer.id if viewer else None,
            event_name="search_degrade",
            props={"keyword": q, "tag_id": tag_id, "plaza_count": len(plaza_rows)},
        )
    )
    try:
        db.commit()
    except Exception:
        db.rollback()

    return {
        "source": "plaza",
        "degraded": True,
        "items": [_card(db, p) for p in plaza_rows[offset : offset + limit]],
        "total": len(plaza_rows),
    }
