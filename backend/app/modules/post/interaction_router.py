"""互动路由：回答 14-16、评论 19-20、点赞/收藏 21-22 + 收藏列表（技术细节文档 §5.4/§5.5）。

V1.3：回答提交/编辑后异步生成 AI 可靠性评分（reliability 场景）。
"""

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import PageParams, get_current_user
from app.core.response import ok
from app.models import Post, User
from app.modules.post import answers, comments, likes
from app.modules.post.service import _card

router = APIRouter()


class AnswerCreateIn(BaseModel):
    content: str = Field(min_length=1, max_length=5000)


@router.post("/posts/{post_id}/answers")
def create_answer(
    post_id: int,
    body: AnswerCreateIn,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    data = answers.create_answer(db, user, post_id, body.content)
    # V1.3：异步生成 AI 可靠性评分（LLM 关闭/失败时任务内部静默）
    background_tasks.add_task(answers.generate_reliability_task, data["id"])
    return ok(data)


@router.put("/answers/{answer_id}")
def update_answer(
    answer_id: int,
    body: AnswerCreateIn,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    data = answers.update_answer(db, user, answer_id, body.content)
    # V1.3：内容已变化 → 重新生成可靠性评分
    background_tasks.add_task(answers.generate_reliability_task, answer_id)
    return ok(data)


@router.delete("/answers/{answer_id}")
def delete_answer(
    answer_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    answers.delete_answer(db, user, answer_id)
    return ok(None)


@router.get("/comments")
def list_comments(
    target_type: int,
    target_id: int,
    db: Session = Depends(get_db),
):
    """评论树查询（回答评论按需拉取；帖子评论已随详情返回）。"""
    return ok(comments.list_comments(db, target_type, target_id))


class CommentCreateIn(BaseModel):
    target_type: int = Field(ge=1, le=3)
    target_id: int
    content: str = Field(min_length=1, max_length=500)
    parent_id: int | None = None
    reply_to_user_id: int | None = None


@router.post("/comments")
def create_comment(
    body: CommentCreateIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return ok(
        comments.create_comment(
            db, user, body.target_type, body.target_id, body.content, body.parent_id, body.reply_to_user_id
        )
    )


@router.delete("/comments/{comment_id}")
def delete_comment(
    comment_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    comments.delete_comment(db, user, comment_id)
    return ok(None)


class TargetIn(BaseModel):
    target_type: int = Field(ge=1, le=3)
    target_id: int


@router.post("/likes/toggle")
def toggle_like(
    body: TargetIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return ok(likes.toggle_like(db, user, body.target_type, body.target_id))


@router.post("/favorites/toggle")
def toggle_favorite(
    body: TargetIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return ok(likes.toggle_favorite(db, user, body.target_type, body.target_id))


@router.get("/favorites")
def list_favorites(
    target_type: int = Query(1, ge=1, le=2, description="1 帖子 2 回答"),
    page: PageParams = Depends(),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """我的收藏列表（个人主页收藏 Tab）：软删目标自动过滤；帖子返回 PostCard。"""
    from app.models import Answer, Favorite

    favs = (
        db.execute(
            select(Favorite)
            .where(Favorite.user_id == user.id, Favorite.target_type == target_type)
            .order_by(Favorite.created_at.desc())
        )
        .scalars()
        .all()
    )
    items = []
    for f in favs:
        if target_type == 1:
            p = db.get(Post, f.target_id)
            if p is not None and p.deleted_at is None:
                items.append(_card(db, p))
        else:
            a = db.get(Answer, f.target_id)
            if a is not None and a.deleted_at is None:
                post = db.get(Post, a.post_id)
                if post is not None and post.deleted_at is None:
                    items.append(
                        {
                            "answer_id": a.id,
                            "post_id": post.id,
                            "post_title": post.title,
                            "content": (a.content or "")[:200],
                            "author_nickname": (
                                db.get(User, a.author_id).nickname
                                if db.get(User, a.author_id)
                                else "已注销"
                            ),
                            "created_at": a.created_at,
                        }
                    )
    return ok({"total": len(items), "items": items[page.offset : page.offset + page.limit]})
