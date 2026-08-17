"""/ai/* 路由(从 main.py 拆出): 健康风险分析 / 快速AI意见。"""

import logging
import time
import uuid

from fastapi import APIRouter, HTTPException
from langchain_core.messages import HumanMessage

from app.runtime import resources, verify_token
from app.api.models import (
    AnalyzeRequest,
    AnalyzeResponse,
    QuickAnalyzeRequest,
    QuickAnalyzeResponse,
)
from app.agents.utils.json_utils import parse_json_output
from app.utils.security import mask_sensitive

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai", tags=["ai"])


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_patient_health_risk(request: AnalyzeRequest):
    """健康风险分析接口 - AI分析病人健康数据并生成建议(复用LLM实例, 直接异步调用)"""
    patient_text = request.data.strip()
    if not patient_text:
        raise HTTPException(status_code=422, detail="data cannot be empty")

    start_time = time.time()
    req_id = uuid.uuid4().hex[:12]

    logger.info("=" * 80)
    logger.info(f"🏥 [请求 {req_id}] 开始健康风险分析")
    logger.info("=" * 80)
    logger.info(f"👤 患者ID: {request.patientId}")
    logger.info(f"📋 数据长度: {len(patient_text)} 字符")
    logger.info(f"📝 数据内容(脱敏): {mask_sensitive(patient_text)[:200]}")
    logger.info("-" * 80)

    try:
        llm_turbo = resources.get("llm_turbo")
        if not llm_turbo:
            raise HTTPException(status_code=503, detail="LLM service not ready")

        # 直接使用 LangChain 异步接口，复用全局 LLM 实例
        prompt = f"""你是三甲医院全科医生。快速分析以下患者信息，给出简洁意见。

患者信息：
{patient_text}

请直接输出 JSON（不要用 markdown 代码块）：
{{
    "riskLevel": "低风险/中风险/高风险",
    "suggestion": "最重要的处置建议（1句，50字以内）",
    "analysisDetails": "健康状况评估摘要（50字以内）"
}}

要求：
- riskLevel 必须是"低风险"、"中风险"、"高风险"之一
- 禁止确诊语气
- 禁止具体药物剂量"""

        # 直接异步调用，无需线程池包装
        response = await llm_turbo.ainvoke([HumanMessage(content=prompt)])
        content = getattr(response, "content", "")

        # 解析JSON(统一走 json_utils, 兼容纯 JSON/代码块/前后说明文字)
        result = parse_json_output(content, {}) or {}
        if not result:
            result = {
                "riskLevel": "中风险",
                "suggestion": "建议结合线下检查结果进一步评估。",
                "analysisDetails": "系统已完成基础风险评估。",
            }

        analysis_time = time.time() - start_time

        logger.info(f"✅ 健康风险分析完成 - 耗时: {analysis_time:.2f}秒")
        logger.info(f"🎯 风险等级: {result.get('riskLevel', 'Unknown')}")
        logger.info(f"💡 建议长度: {len(result.get('suggestion', ''))} 字符")
        logger.info(f"📊 分析详情长度: {len(result.get('analysisDetails', ''))} 字符")
        logger.info("-" * 80)
        logger.info(f"🟢 [请求 {req_id}] 健康风险分析完成")
        logger.info("=" * 80)

        return {
            "code": 1,
            "msg": "success",
            "data": {
                "riskLevel": result.get('riskLevel', '中风险'),
                "suggestion": result.get('suggestion', ''),
                "analysisDetails": result.get('analysisDetails', '')
            }
        }
    except Exception as e:
        error_time = time.time() - start_time
        logger.error(f"❌ [请求 {req_id}] 健康风险分析失败 - 耗时: {error_time:.2f}秒")
        logger.error(f"     错误类型: {type(e).__name__}")
        logger.error(f"     错误信息: {str(e)}")
        logger.error("=" * 80)
        raise HTTPException(status_code=500, detail=f"健康风险分析失败: {str(e)}")


@router.post("/quick-analyze", response_model=QuickAnalyzeResponse)
async def quick_analyze(request: QuickAnalyzeRequest):
    """快速AI意见接口 - 跳过多专家推理，直接生成快速意见"""
    verify_token(request.token)

    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=422, detail="question cannot be empty")

    start_time = time.time()
    req_id = uuid.uuid4().hex[:12]

    logger.info("=" * 80)
    logger.info(f"⚡ [请求 {req_id}] 开始快速AI意见分析")
    logger.info("=" * 80)
    logger.info(f"📝 问题内容: {question[:200]}{'...' if len(question) > 200 else ''}")
    logger.info(f"📊 问题长度: {len(question)} 字符")
    logger.info("-" * 80)

    try:
        llm_turbo = resources.get("llm_turbo")
        if not llm_turbo:
            raise HTTPException(status_code=503, detail="LLM service not ready")

        prompt = f"""你是三甲医院神经内科主任医师。请快速分析以下临床问题，给出简洁专业的意见。

问题：
{question}

请直接输出 JSON（不要用 markdown 代码块包裹）：
{{
    "quickOpinion": "快速专业意见（100字以内）",
    "keyPoints": ["关键点1", "关键点2", "关键点3"],
    "riskLevel": "低风险/中风险/高风险"
}}

要求：
- quickOpinion: 简洁专业，禁止确诊语气
- keyPoints: 3-5个关键点，每点20字以内
- riskLevel: 基于问题内容判断风险等级
- 禁止具体药物剂量"""

        response = await llm_turbo.ainvoke([HumanMessage(content=prompt)])
        content = getattr(response, "content", "")

        result = parse_json_output(content, {}) or {}
        if not result:
            result = {
                "quickOpinion": "建议结合临床实际进一步评估，如症状加重请及时就医。",
                "keyPoints": ["需进一步检查", "结合临床判断", "及时就医"],
                "riskLevel": "中风险"
            }

        analysis_time = time.time() - start_time

        logger.info(f"✅ 快速AI意见分析完成 - 耗时: {analysis_time:.2f}秒")
        logger.info(f"💬 意见长度: {len(result.get('quickOpinion', ''))} 字符")
        logger.info(f"📋 关键点数: {len(result.get('keyPoints', []))}")
        logger.info(f"🎯 风险等级: {result.get('riskLevel', 'Unknown')}")
        logger.info("-" * 80)
        logger.info(f"🟢 [请求 {req_id}] 快速AI意见分析完成")
        logger.info("=" * 80)

        return {
            "code": 1,
            "msg": "success",
            "data": result
        }
    except Exception as e:
        error_time = time.time() - start_time
        logger.error(f"❌ [请求 {req_id}] 快速AI意见分析失败 - 耗时: {error_time:.2f}秒")
        logger.error(f"     错误类型: {type(e).__name__}")
        logger.error(f"     错误信息: {str(e)}")
        logger.error("=" * 80)
        raise HTTPException(status_code=500, detail=f"快速AI意见分析失败: {str(e)}")
