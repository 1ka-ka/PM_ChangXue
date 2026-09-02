"""健康检查与连通性验证端点。"""

from fastapi import APIRouter

from app.core.response import ok

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    """服务健康检查。"""
    return ok({"status": "up"})


@router.get("/echo")
def echo(n: int) -> dict:
    """连通性与参数校验验证端点（S0 冒烟测试用：缺参/错型触发 40001 信封）。"""
    return ok({"n": n})
