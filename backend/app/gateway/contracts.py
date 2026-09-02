"""LLM 网关五场景契约（ARCH §6，P0 仅契约零调用）。

P0 交付物：Pydantic 契约模型 + 场景→模型路由表。
P1 在 gateway/client.py 实现 GatewayClient.invoke(scene, payload)（超时 10s/重试/降级/调用日志），
在此之前整个 gateway 目录不包含任何外部 HTTP 调用代码路径（LLM_ENABLED=False 兜底）。
"""

from typing import Literal

from pydantic import BaseModel, Field

# 场景 → 默认模型（ARCH §6；配置驱动。V1.2 起接入阿里云百炼 DashScope）
SCENE_MODEL_MAP = {
    "summary": "qwen-turbo",      # 轻量摘要：快+省
    "ref_answer": "qwen-plus",    # 参考回答：需推理能力
    "reliability": "qwen-plus",   # 可靠性评分：需推理能力
    "quality": "qwen-plus",       # 质量检测：需判别能力
    "moderation": "qwen-plus",    # 违规分级：需判别能力
}


# ---- 1. summary 发帖摘要 ----


class SummaryInput(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    content: str = ""
    images_text: list[str] = Field(default_factory=list, description="图片 OCR 文本")


class SummaryOutput(BaseModel):
    summary: str = Field(max_length=100)
    need_review: bool = Field(description="AI 摘要置信度低时需作者复核")


# ---- 2. ref_answer 参考回答 ----


class RefAnswerInput(BaseModel):
    post_id: int
    title: str = Field(min_length=1)
    content: str = ""
    tag_names: list[str] = Field(default_factory=list)


class RefAnswerOutput(BaseModel):
    answer_text: str
    confidence: float = Field(ge=0, le=1)


# ---- 3. reliability 回答可靠性 ----


class ReliabilityInput(BaseModel):
    post_id: int
    post_title: str
    post_content: str = ""
    answer_text: str


class ReliabilityOutput(BaseModel):
    score: int = Field(ge=0, le=100)
    level: Literal["高", "中", "存疑"]


# ---- 4. quality 回答质量检测 ----


class QualityInput(BaseModel):
    answer_text: str
    author_history: list[str] = Field(default_factory=list, description="用户历史回答样本")


class QualityOutput(BaseModel):
    is_low_quality: bool
    reason: str = ""


# ---- 5. moderation 违规分级 ----


class ModerationInput(BaseModel):
    content: str = Field(min_length=1)


class ModerationOutput(BaseModel):
    level: Literal["极高", "高", "低"]
    violation_type: str | None = None


SCENE_CONTRACTS: dict[str, tuple[type[BaseModel], type[BaseModel]]] = {
    "summary": (SummaryInput, SummaryOutput),
    "ref_answer": (RefAnswerInput, RefAnswerOutput),
    "reliability": (ReliabilityInput, ReliabilityOutput),
    "quality": (QualityInput, QualityOutput),
    "moderation": (ModerationInput, ModerationOutput),
}
