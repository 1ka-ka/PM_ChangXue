"""ORM 表模型包：全量表定义见技术细节文档 §3。"""

from app.models.account import CreditAccount, CreditLog, SmsCode, User
from app.models.enums import TargetType
from app.models.governance import AdminActionLog, AppConfig, Notification, Report, TrackingEvent
from app.models.mall import MallExchange, MallProduct
from app.models.message import DmConversation, DmMessage
from app.models.post import Answer, Comment, Favorite, LikeRecord, Post, PostTag, Tag
from app.models.rank import GratitudeStat, KnowledgeItem, RankSnapshot

__all__ = [
    "User",
    "CreditAccount",
    "CreditLog",
    "SmsCode",
    "TargetType",
    "AdminActionLog",
    "AppConfig",
    "Notification",
    "Report",
    "TrackingEvent",
    "Answer",
    "Comment",
    "Favorite",
    "LikeRecord",
    "Post",
    "PostTag",
    "Tag",
    "GratitudeStat",
    "KnowledgeItem",
    "RankSnapshot",
    "DmConversation",
    "DmMessage",
    "MallProduct",
    "MallExchange",
]
