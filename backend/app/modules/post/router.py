"""post 路由：接口 9-12 + 我的帖子 + 配图上传（技术细节文档 §5.3）。"""

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Query, UploadFile
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import PageParams, get_current_user
from app.core.exceptions import BizError, ErrCode
from app.core.response import ok
from app.models import Post, User
from app.modules.account.router import optional_user
from app.modules.post import service
from app.modules.post.schemas import PostCreateIn, PostUpdateIn

router = APIRouter()


@router.get("/tags")
def list_tags(db: Session = Depends(get_db)):
    """公开标签列表（发帖选择用）：仅启用标签，按 sort 排序。"""
    from sqlalchemy import select

    from app.models import Tag

    rows = db.execute(select(Tag).where(Tag.enabled == 1).order_by(Tag.sort, Tag.id)).scalars().all()
    return ok({"items": [{"id": t.id, "name": t.name, "sort": t.sort} for t in rows]})


@router.post("/uploads/image")
async def upload_image(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    """发帖配图上传：magic bytes + 压缩至 1280px，返回 URL（提交帖时填入 images[]）。"""
    from app.modules.account import service as account_service

    data = await file.read()
    ext = Path(file.filename or "").suffix
    url = account_service.save_image(data, ext, max_px=1280, prefix="post")
    return ok({"url": url})


@router.post("/posts")
def create_post(
    body: PostCreateIn,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    data = service.create_post(db, user, body.title, body.content, body.images, body.tag_ids, body.reward)
    # AI 摘要异步生成（V1.2）：LLM 关闭/失败时任务内部静默降级
    background_tasks.add_task(service.generate_ai_summary_task, data["id"])
    return ok(data)


@router.get("/posts/similar")
def similar_by_query(
    q: str = Query(..., min_length=2, max_length=100, description="待发标题关键词"),
    tag_ids: str | None = Query(None, description="逗号分隔标签 id，如 1,3"),
    limit: int = Query(5, ge=1, le=10),
    db: Session = Depends(get_db),
):
    """发帖页防重复：按标题（+标签）推荐相似历史帖，未登录可用。"""
    ids = [int(x) for x in tag_ids.split(",") if x.strip().isdigit()] if tag_ids else []
    return ok({"items": service.similar_posts(db, q, ids, limit=limit)})


@router.get("/posts/{post_id}")
def get_post(
    post_id: int,
    viewer: User | None = Depends(optional_user),
    db: Session = Depends(get_db),
):
    data = service.get_detail(db, post_id, viewer)
    # 详情附回答列表与帖子根评论树（技术细节文档接口 10）
    from app.modules.post import answers, comments

    data["answers"] = answers.list_answers(db, post_id, viewer)
    data["comments"] = comments.list_comments(db, 1, post_id)
    return ok(data)


@router.get("/posts/{post_id}/similar")
def similar_of_post(
    post_id: int,
    limit: int = Query(5, ge=1, le=10),
    db: Session = Depends(get_db),
):
    """详情页"相关问题"：按本帖标题+标签推荐相似帖（排除自身）。"""
    post = db.get(Post, post_id)
    if post is None or post.deleted_at is not None:
        raise BizError(ErrCode.NOT_FOUND, "帖子不存在或已删除")
    tag_ids = [t.id for t in service._tags_of(db, post_id)]
    return ok({"items": service.similar_posts(db, post.title, tag_ids, exclude_id=post_id, limit=limit)})


@router.put("/posts/{post_id}")
def update_post(
    post_id: int,
    body: PostUpdateIn,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    data = service.update_post(db, user, post_id, body.title, body.content, body.images, body.tag_ids)
    # 编辑窗口内改了内容 → 重新生成 AI 摘要
    background_tasks.add_task(service.generate_ai_summary_task, post_id)
    return ok(data)


@router.delete("/posts/{post_id}")
def delete_post(
    post_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service.delete_post(db, user, post_id)
    return ok(None)


@router.get("/account/my-posts")
def my_posts(
    status: int | None = Query(None, description="0待解决 1已解决，缺省全部"),
    page: PageParams = Depends(),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return ok(service.my_posts(db, user.id, status, page.offset, page.limit))
