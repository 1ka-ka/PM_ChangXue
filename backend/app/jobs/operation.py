"""系统运营定时任务（V1.13）：拟真节奏调度。

- 每 OP_TICK_MINUTES 分钟一轮：工作时段（8-23 点）+ 概率闸门（OP_ACT_PROBABILITY）
  实现动作在一天内随机分布；配额（每日 3 提问 / 10 互动上限）由 service 动作内部把关
- OP_ENABLED / LLM 关闭时：动作池自动退化为免 LLM 动作（采纳/点赞），再无可做则空转
- 测试环境不注册调度
"""

from app.core.config import settings


def register(scheduler) -> None:
    """注册到调度器（main lifespan 调用；测试环境不注册）。"""
    from app.modules.operation.service import run_scheduled_tick

    scheduler.add_job(
        run_scheduled_tick,
        "interval",
        minutes=settings.OP_TICK_MINUTES,
        id="operation_tick",
    )
