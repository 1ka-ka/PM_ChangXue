"""mall 模块入参模型（V1.8 积分商城）。"""

from pydantic import BaseModel, Field


class ExchangeIn(BaseModel):
    """兑换商品：仅需商品 id（价格/库存以服务端为准）。"""

    product_id: int = Field(gt=0)
