"""/admin/* 路由(从 main.py 拆出): 配置热更新 / 报告模式列表。"""

import logging
import time
import uuid

from fastapi import APIRouter, HTTPException

from app.config.config_loader import (
    get_prompt_manager,
    get_report_manager,
    get_expert_manager,
    get_validation_manager,
    get_limits_manager,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/reload_config")
async def reload_config():
    """配置热更新接口 - 增强日志版本"""
    start_time = time.time()
    req_id = uuid.uuid4().hex[:12]

    logger.info("=" * 80)
    logger.info(f"🔄 [请求 {req_id}] 开始配置热更新")
    logger.info("=" * 80)

    try:
        logger.info("📋 重新加载Prompt配置...")
        get_prompt_manager().reload()
        logger.info("✅ Prompt配置重新加载完成")

        logger.info("📋 重新加载报告配置...")
        get_report_manager().reload()
        logger.info("✅ 报告配置重新加载完成")

        logger.info("📋 重新加载专家配置...")
        get_expert_manager().reload()
        logger.info("✅ 专家配置重新加载完成")

        logger.info("📋 重新加载校验配置...")
        get_validation_manager().reload()
        logger.info("✅ 校验配置重新加载完成")

        logger.info("📋 重新加载参数限制配置...")
        get_limits_manager().reload()
        logger.info("✅ 参数限制配置重新加载完成")

        reload_time = time.time() - start_time
        logger.info("-" * 80)
        logger.info(f"✅ 所有配置重新加载完成 - 耗时: {reload_time:.2f}秒")
        logger.info(f"🟢 [请求 {req_id}] 配置热更新完成")
        logger.info("=" * 80)

        return {"status": "ok", "message": "配置已热更新"}
    except Exception as e:
        error_time = time.time() - start_time
        logger.error(f"❌ [请求 {req_id}] 配置热更新失败 - 耗时: {error_time:.2f}秒")
        logger.error(f"     错误类型: {type(e).__name__}")
        logger.error(f"     错误信息: {str(e)}")
        logger.error("=" * 80)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/report_modes")
async def list_report_modes():
    """获取可用报告模式接口 - 增强日志版本"""
    req_id = uuid.uuid4().hex[:12]

    logger.info(f"📋 [请求 {req_id}] 获取可用报告模式")

    mgr = get_report_manager()
    modes = mgr.list_modes()

    logger.info(f"✅ 可用报告模式: {modes}")

    return {
        "modes": [
            {"key": m, "name": mgr.get_template_name(m)}
            for m in modes
        ]
    }
