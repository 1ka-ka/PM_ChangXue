"""榜单结算定时任务（交付文档 S8）。

- 每周一 00:05 结算上周感谢值 → rank_snapshot（周）
- 每月 1 日 00:05 结算上月感谢值 → rank_snapshot（月）
- 失败重试 3 次；仍失败则保留上期快照（查询侧 settling 标记降级）

settle 幂等（先清后写），重试不会产生重复快照。
"""

import logging
from datetime import datetime

from app.core.database import SessionLocal
from app.modules.rank import service as rank_service

logger = logging.getLogger("changxue.settle")

RETRY = 3


def settle_with_retry(period_type: int, period_key: str) -> bool:
    for attempt in range(1, RETRY + 1):
        try:
            with SessionLocal() as db:
                n = rank_service.settle(db, period_type, period_key)
            logger.info("榜单结算成功 period_type=%s key=%s rows=%s", period_type, period_key, n)
            return True
        except Exception:
            logger.exception(
                "榜单结算失败(%s/%s) period_type=%s key=%s", attempt, RETRY, period_type, period_key
            )
    return False


def run_weekly() -> None:
    """周一 00:05 触发：结算上一个完整自然周。"""
    key = rank_service.prev_keys()[1]
    settle_with_retry(1, key)


def run_monthly() -> None:
    """每月 1 日 00:05 触发：结算上一个完整自然月。"""
    key = rank_service.prev_keys()[2]
    settle_with_retry(2, key)


def start_scheduler(app_env: str):
    """启动定时调度（测试环境跳过；幂等可重复调用）。"""
    if app_env == "test":
        return None
    from apscheduler.schedulers.background import BackgroundScheduler

    scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
    scheduler.add_job(run_weekly, "cron", day_of_week="mon", hour=0, minute=5, id="settle_week")
    scheduler.add_job(run_monthly, "cron", day=1, hour=0, minute=5, id="settle_month")
    scheduler.start()
    return scheduler
