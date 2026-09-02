"""应用入口：中间件、异常处理器、路由注册（ARCH §2 main.py）。"""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import health
from app.core.config import settings
from app.core.exceptions import BizError, ErrCode
from app.modules.account.router import router as account_router
from app.modules.credit.router import router as credit_router
from app.modules.post.router import router as post_router


def create_app() -> FastAPI:
    app = FastAPI(title="畅学社区 API", version="0.1.0")

    # CORS：本地前端 Vite 开发服务器
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 路由注册（后续阶段在此追加各业务模块 router）
    app.include_router(health.router, prefix="/api")
    app.include_router(account_router, prefix="/api")
    app.include_router(credit_router, prefix="/api")
    app.include_router(post_router, prefix="/api")

    # 上传文件静态服务（头像/帖子图片）
    from pathlib import Path

    upload_dir = Path(settings.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/uploads", StaticFiles(directory=str(upload_dir)), name="uploads")

    # ---- 全局异常处理：统一转响应信封（技术细节文档 §2.1/§2.2）----

    @app.exception_handler(BizError)
    async def biz_error_handler(request: Request, exc: BizError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.http_status,
            content={"code": exc.code, "msg": exc.msg, "data": None},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # 取第一条校验错误，转 40001 信封（HTTP 200）
        errors = exc.errors()
        first = errors[0] if errors else {}
        loc = ".".join(str(x) for x in first.get("loc", []) if x != "query")
        detail = first.get("msg", "invalid")
        msg = f"参数错误: {loc} {detail}" if loc else f"参数错误: {detail}"
        return JSONResponse(
            status_code=200,
            content={"code": ErrCode.BAD_REQUEST, "msg": msg, "data": None},
        )

    @app.exception_handler(Exception)
    async def fallback_handler(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={"code": ErrCode.INTERNAL, "msg": "服务器内部错误", "data": None},
        )

    return app


app = create_app()
