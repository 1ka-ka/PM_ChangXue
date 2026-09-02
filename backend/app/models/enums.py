"""通用类型：目标类型枚举（技术细节文档 §2.6）。

target_type 复用于：点赞/收藏/举报/通知。
"""

from enum import IntEnum


class TargetType(IntEnum):
    POST = 1      # 帖子
    ANSWER = 2    # 回答
    COMMENT = 3   # 评论
