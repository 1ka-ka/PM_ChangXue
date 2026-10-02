"""post 模块 Pydantic 模型（技术细节文档 §4 PostCreate/PostDetail）。"""

from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class PostCreateIn(BaseModel):
    title: str = Field(min_length=1, max_length=50)
    content: str = Field(default="", max_length=5000)
    images: list[str] = Field(default_factory=list, max_length=9)
    tag_ids: list[int] = Field(min_length=1, max_length=3)
    reward: int = 0  # 悬赏档位：0/10/20/50/100


class PostUpdateIn(BaseModel):
    title: str = Field(min_length=1, max_length=50)
    content: str = Field(default="", max_length=5000)
    images: list[str] = Field(default_factory=list, max_length=9)
    tag_ids: list[int] = Field(min_length=1, max_length=3)


class TagItem(BaseModel):
    id: int
    name: str


class PostCard(BaseModel):
    """列表卡片（技术细节文档 §4）。"""

    id: int
    title: str
    summary: str  # content 截断 100 字
    author_id: int
    author_nickname: str
    status: int  # 0待解决 1已解决
    reward: int
    answer_count: int
    like_count: int
    view_count: int
    tags: list[TagItem]
    is_rewarded: bool = False  # 悬赏标记
    no_answer_days: int | None = None  # 待解决帖超阈值无新回答时非 null（PRD §6.1）
    is_ai_summary: bool = False  # summary 为 AI 生成摘要（V1.2），否则为正文截断
    created_at: datetime


class PostDetail(PostCard):
    content: str
    images: list[str] = []
    is_liked: bool = False
    is_favorite: bool = False
    edited: bool = False
    ai_summary: str | None = None  # AI 摘要全文（生成中/降级时为 null）


# ---- 个人中心（V1.12）：我的回答/评论/点赞 + 他人公开内容 ----


class MyAnswerItem(BaseModel):
    """我的回答列表项（个人中心/他人主页共用）。"""

    id: int
    post_id: int
    post_title: str | None = None  # 所属帖被删时 null（前端显示「原提问已删除」）
    post_status: int | None = None
    content: str
    is_accepted: bool
    is_best: bool
    like_count: int
    created_at: datetime


class MyCommentItem(BaseModel):
    """我的评论列表项。"""

    id: int
    target_type: int  # 1帖子 2回答
    target_id: int
    post_id: int | None = None  # 回答评论时为其所属帖（点击跳转用）；目标已删时 null
    post_title: str | None = None
    content: str
    created_at: datetime


class MyLikeItem(BaseModel):
    """我的点赞列表项（帖+答混合，target_type 区分）。"""

    target_type: int  # 1帖 2答 3评论
    target_id: int
    post_id: int | None = None  # 点击跳转用
    post_title: str | None = None
    content: str  # 目标内容（评论为其内容；回答为内容；帖子为标题）
    author_nickname: str | None = None  # 目标作者（评论点赞时为评论者）
    created_at: datetime
