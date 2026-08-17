"""模型服务运行时状态与鉴权(从 main.py 拆出, 供路由/引导模块共享)。

- resources: 全局资源容器(agent/retriever/model_router/vision_service 等), 由 bootstrap 填充;
- _KbJobs: 知识库热更新后台任务表;
- verify_token: JWT 校验(返回解码 payload, 含用户 id)。
"""

import logging
import os
import uuid
import time

import jwt
from fastapi import HTTPException

logger = logging.getLogger(__name__)

SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-here")
ALGORITHM = "HS256"

# 全局资源容器: 由 bootstrap.lifespan 填充, 各路由按需读取
resources = {}

# 知识库热更新后台任务表 {job_id: {status, action, started, finished, stats, error}}
_KbJobs = {}


def verify_token(token: str) -> dict:
    """校验 JWT 并返回解码 payload(含用户 id, 供并发闸/审计使用)。"""
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")


def start_kb_job(action: str) -> str:
    """后台执行知识库热更新(reload), 返回 job_id 供前端轮询状态。"""
    job_id = uuid.uuid4().hex[:12]
    _KbJobs[job_id] = {"status": "running", "action": action, "started": time.time(),
                       "finished": None, "stats": None, "error": None}

    def _run():
        try:
            retriever = resources.get("retriever")
            if not retriever:
                raise RuntimeError("检索引擎未就绪")
            stats = retriever.reload()
            _KbJobs[job_id].update(status="done", finished=time.time(), stats=stats)
        except Exception as e:  # noqa: BLE001
            logger.error(f"[KB] 热更新失败: {e}")
            _KbJobs[job_id].update(status="error", finished=time.time(), error=str(e)[:300])

    import threading
    threading.Thread(target=_run, daemon=True).start()
    return job_id
