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
    created_at: datetime


class PostDetail(PostCard):
    content: str
    images: list[str] = []
    is_liked: bool = False
    is_favorite: bool = False
    edited: bool = False
