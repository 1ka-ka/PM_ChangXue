"""post 路由：接口 9-12 + 我的帖子（技术细节文档 §5.3）。"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import PageParams, get_current_user
from app.core.response import ok
from app.models import User
from app.modules.account.router import optional_user
from app.modules.post import service
from app.modules.post.schemas import PostCreateIn, PostUpdateIn

router = APIRouter()


@router.post("/posts")
def create_post(
    body: PostCreateIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return ok(service.create_post(db, user, body.title, body.content, body.images, body.tag_ids, body.reward))


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


@router.put("/posts/{post_id}")
def update_post(
    post_id: int,
    body: PostUpdateIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return ok(
        service.update_post(db, user, post_id, body.title, body.content, body.images, body.tag_ids)
    )


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
