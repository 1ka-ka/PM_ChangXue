"""message 模块入参模型（V1.7 私信）。"""

from pydantic import BaseModel, Field, model_validator


class DmSendIn(BaseModel):
    """发送私信：纯文本 1-500 字（敏感词在 service 层拦截）。"""

    to_user_id: int = Field(gt=0)
    content: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def strip_content(self):
        self.content = self.content.strip()
        if not self.content:
            raise ValueError("content 不能为空白")
        return self
