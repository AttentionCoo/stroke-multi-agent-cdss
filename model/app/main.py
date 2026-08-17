"""模型服务入口(瘦身后): 应用组装 + 健康检查 + 对外兼容导出。

职责拆分后的结构:
- app/bootstrap.py      资源初始化与生命周期(lifespan/init_all_resources)
- app/runtime.py        运行时状态容器(resources/_KbJobs)与 JWT 鉴权
- app/api/models.py     API 请求/响应模型
- app/api/routes_model.py  /model/*  临床推理流/HITL续跑/知识库/运行时信息/工具/检索
- app/api/routes_ai.py     /ai/*     健康风险分析/快速AI意见
- app/api/routes_admin.py  /admin/*  配置热更新/报告模式

本文件仅保留: FastAPI 实例组装、CORS、/health、路由注册,
以及为既有测试提供稳定导入路径的兼容导出。
"""

import logging
import os
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from app.bootstrap import lifespan
from app.runtime import resources, verify_token
from app.api.models import QueryRequest, _validate_kb_files
from app.api.routes_model import model_info, router as model_router
from app.api.routes_ai import router as ai_router
from app.api.routes_admin import router as admin_router


os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

# 配置日志系统
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("app.log", encoding="utf-8")
    ]
)

logger = logging.getLogger(__name__)

app = FastAPI(lifespan=lifespan)

# 阶段7: CORS 默认关闭(前端经网关同源代理访问); 设置 MODEL_CORS_ORIGINS 时按逗号分隔放行
_cors_origins = [o.strip() for o in os.getenv("MODEL_CORS_ORIGINS", "").split(",") if o.strip()]
if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.get("/health")
async def health_check():
    """容器健康检查接口。

    模型未就绪时返回 503(而非 200), 使 docker healthcheck 与
    depends_on: service_healthy 真正等到推理服务加载完成,
    避免后端在模型冷启动期间转发请求导致"AI 服务暂时不可用"。
    """
    from fastapi.responses import JSONResponse
    ready = resources.get("model") is not None
    return JSONResponse(
        status_code=200 if ready else 503,
        content={
            "status": "ready" if ready else "starting",
            "model_loaded": ready,
        },
    )


# 路由注册
app.include_router(model_router)
app.include_router(ai_router)
app.include_router(admin_router)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
