"""统一响应信封（技术细节文档 §2.1）。

成功：{"code": 0, "msg": "ok", "data": {...}}
失败：{"code": 40101, "msg": "账号或密码错误", "data": null}
"""

from typing import Any


def ok(data: Any = None, msg: str = "ok") -> dict:
    """构造成功信封。所有接口统一返回该结构。"""
    return {"code": 0, "msg": msg, "data": data}
