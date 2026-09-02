"""积分流水 source 枚举（技术细节文档 §3.1 credit_log.source）。"""

from enum import IntEnum


class CreditSource(IntEnum):
    REGISTER = 1      # 注册赠送
    DAILY_LOGIN = 2   # 每日登录
    TASK = 3          # 日常任务（P1）
    ACCEPTED = 4      # 回答被采纳
    REWARD = 5        # 悬赏消耗（负）
    RECALL = 6        # 质量追回（负）
    SHOP = 7          # 商城消耗（P2，负）

    @property
    def is_income(self) -> bool:
        """产出类：计入日封顶统计。"""
        return self in (self.REGISTER, self.DAILY_LOGIN, self.TASK, self.ACCEPTED)

    @property
    def label(self) -> str:
        return {
            1: "注册赠送",
            2: "每日登录",
            3: "任务奖励",
            4: "回答被采纳",
            5: "悬赏支出",
            6: "积分追回",
            7: "商城兑换",
        }[self.value]


SOURCE_TEXT = {s.value: s.label for s in CreditSource}
