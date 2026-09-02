"""pytest 全局夹具：测试环境变量 + HTTP 客户端（SQLite 内存库）。"""

import os

# 必须在导入 app 之前设置环境变量
os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite://"  # 内存库
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["UPLOAD_DIR"] = "./uploads_test"  # 测试上传目录（.gitignore 覆盖 uploads* 不污染仓库）
os.environ["LLM_ENABLED"] = "false"  # 测试环境禁用真实 LLM 调用（V1.2）
os.environ["LLM_API_KEY"] = ""  # 并显式清空 Key（防 .env 泄入测试进程）

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402
from app import models  # noqa: E402, F401  # 触发全部模型注册


@pytest.fixture(scope="session", autouse=True)
def _create_tables():
    """session 级建表：所有测试模块共享同一内存库结构。"""
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture()
def client() -> TestClient:
    """同步测试客户端，直连 ASGI 应用不占用端口（底层基于 httpx）。"""
    with TestClient(app) as c:
        yield c
