"""pytest 全局夹具：测试环境变量 + HTTP 客户端（SQLite 内存库）。"""

import os

# 必须在导入 app 之前设置环境变量
os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite://"  # 内存库
os.environ["SECRET_KEY"] = "test-secret-key"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture()
def client() -> TestClient:
    """同步测试客户端，直连 ASGI 应用不占用端口（底层基于 httpx）。"""
    with TestClient(app) as c:
        yield c
