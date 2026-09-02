"""依赖注入（ARCH §2 core/deps.py）。

S0 仅提供分页参数依赖；当前用户依赖在 S2 认证模块实现后补充。
"""

from fastapi import Query


class PageParams:
    """分页参数依赖（技术细节文档 §2.4）：?page=1&page_size=20，page_size 上限 50。"""

    def __init__(
        self,
        page: int = Query(1, ge=1, description="页码，从 1 开始"),
        page_size: int = Query(20, ge=1, le=50, description="每页条数，上限 50"),
    ):
        self.page = page
        self.page_size = page_size

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        return self.page_size
