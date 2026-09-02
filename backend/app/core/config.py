"""全局配置（技术细节文档 §1.3）。

读取顺序：环境变量 / .env 文件 > 此处默认值。
生产环境可通过 app_config 表运行时覆盖（S1 实现），当前以 env 为准。
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ---- 环境 ----
    APP_ENV: str = "dev"  # dev / test / prod
    DATABASE_URL: str = "sqlite:///./changxue.db"  # prod: mysql+pymysql://user:pwd@host/db
    SECRET_KEY: str = "dev-secret-change-me"  # 生产必须通过环境变量覆盖
    ACCESS_TOKEN_EXPIRE_HOURS: int = 168  # 登录态 7 天
    CORS_ORIGINS: list[str] = ["http://localhost:5173"]

    # ---- 积分参数（PRD §6.3，全部可配）----
    CREDIT_REGISTER: int = 50
    CREDIT_DAILY_LOGIN: int = 5
    CREDIT_ACCEPT: int = 30
    REWARD_TIERS: list[int] = [10, 20, 50, 100]
    CREDIT_DAILY_CAP: int = 100

    # ---- 状态机与推荐参数（PRD §6.1）----
    NO_ANSWER_MARK_DAYS: int = 7  # “已 X 天未有回答”标注阈值
    DECAY_DAYS: int = 14  # 推荐衰减阈值
    ACCEPT_MAX: int = 3  # 每帖采纳上限

    # ---- 上传 ----
    UPLOAD_DIR: str = "./uploads"
    IMAGE_MAX_COUNT: int = 9
    IMAGE_MAX_SIZE_MB: int = 5
    IMAGE_ALLOWED_EXT: list[str] = ["jpg", "jpeg", "png", "webp"]

    # ---- 业务上限 ----
    TITLE_MAX_LEN: int = 50
    CONTENT_MAX_LEN: int = 5000
    COMMENT_MAX_LEN: int = 500
    TAG_MAX_PER_POST: int = 3
    RANK_TOP_N: int = 10

    # ---- LLM 网关（V1.2 起接入；.env 提供 Key，测试环境恒关）----
    LLM_ENABLED: bool = False
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    LLM_TIMEOUT_SECONDS: int = 10
    LLM_MAX_RETRIES: int = 2  # 首次 + 重试次数


settings = Settings()
