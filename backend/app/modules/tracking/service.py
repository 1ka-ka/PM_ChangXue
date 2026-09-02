"""埋点：内存令牌桶限流 + 批量落库（失败静默，ARCH §7.4）。

- 令牌桶：60 次/分/IP，进程内存实现（单体部署足够；P2 多 worker 再换 Redis）
- 落库失败丢弃：埋点不承诺 100%，任何异常不外抛
"""

import logging
import threading
import time
from collections import defaultdict

from sqlalchemy.orm import Session

from app.models import TrackingEvent, User

logger = logging.getLogger("changxue.tracking")

RATE_LIMIT_PER_MIN = 60
MAX_EVENTS_PER_BATCH = 20


class TokenBucket:
    """单 IP 令牌桶：容量=速率=60，惰性补充。"""

    __slots__ = ("tokens", "last")

    def __init__(self):
        self.tokens = float(RATE_LIMIT_PER_MIN)
        self.last = time.monotonic()

    def allow(self) -> bool:
        now = time.monotonic()
        self.tokens = min(RATE_LIMIT_PER_MIN, self.tokens + (now - self.last) * (RATE_LIMIT_PER_MIN / 60))
        self.last = now
        if self.tokens >= 1:
            self.tokens -= 1
            return True
        return False


class RateLimiter:
    def __init__(self):
        self._buckets: dict[str, TokenBucket] = defaultdict(TokenBucket)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        with self._lock:
            return self._buckets[key].allow()


limiter = RateLimiter()


def ingest_batch(db: Session, user: User | None, events: list[dict]) -> bool:
    """批量落库：单条构造失败或整批异常均静默丢弃，返回是否全部成功。

    events: [{name, props}]；name 校验由 Pydantic 完成，此处仅防御。
    """
    try:
        for e in events:
            name = (e.get("name") or "").strip()
            if not name or len(name) > 50:
                continue
            db.add(
                TrackingEvent(
                    user_id=user.id if user else None,
                    event_name=name,
                    props=e.get("props"),
                )
            )
        db.commit()
        return True
    except Exception:
        db.rollback()
        logger.warning("埋点落库失败已丢弃", exc_info=True)
        return False
