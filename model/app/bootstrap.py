"""系统引导(bootstrap): 资源初始化与生命周期管理(从 main.py 拆出)。

- init_all_resources: 加载配置/LLM/检索/助手/智能体/附属服务;
- lifespan: FastAPI 启动/关闭钩子(检查点在主事件循环内创建)。
"""

import asyncio
import concurrent.futures
import logging
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.runtime import resources
from app.config.config_loader import (
    get_prompt_manager,
    get_report_manager,
    get_expert_manager,
    get_validation_manager,
    get_limits_manager,
)
from app.config.model_router import ModelRouter
from app.agents.assistant import MedicalAssistant
from app.agents.orchestrators.qwen_agent import QwenAgent
from app.agents.orchestrators.checkpoint import open_checkpointer
from app.rag.retrievers import UnifiedSearchEngine, CONFIG
from app.services.vision_service import VisionAnalysisService
from app.utils.context_summary import ConversationSummaryService
from app.utils.naming_model import NamingModel
from app.utils.security import RequestConcurrencyGuard
from app.utils.usage import UsageCallbackHandler

logger = logging.getLogger(__name__)


def init_all_resources(checkpointer=None):
    """初始化所有资源(可选注入 LangGraph checkpointer)。"""
    start_time = time.time()
    logger.info("=" * 80)
    logger.info("🚀 开始初始化系统资源")
    logger.info("=" * 80)

    # 步骤1: 加载配置管理器
    logger.info("📋 [1/7] 加载配置管理器...")
    prompt_mgr = get_prompt_manager()
    report_mgr = get_report_manager()
    expert_mgr = get_expert_manager()
    validation_mgr = get_validation_manager()
    limits_mgr = get_limits_manager()

    # 显示配置信息
    logger.info(f"  ✅ Prompt管理器: 已加载 {len(prompt_mgr._prompts)} 个prompt模板")
    logger.info(f"  ✅ 报告管理器: 可用模式 {report_mgr.list_modes()}")

    # 显示专家配置
    experts = expert_mgr.get_experts()
    logger.info(f"  ✅ 专家配置: 已加载 {len(experts)} 位专家")
    for expert in experts:
        logger.info(f"     - {expert.get('role')} (优先级: {expert.get('priority')})")

    # 显示校验配置
    rules = validation_mgr.get_contraindication_rules()
    logger.info(f"  ✅ 校验配置: {len(rules)} 个治疗方式的禁忌症规则")
    logger.info(f"     - 最大反思次数: {validation_mgr.get_max_reflection_count()}")
    logger.info(f"     - 规则引擎: {'启用' if validation_mgr.is_rule_engine_enabled() else '禁用'}")
    logger.info(f"     - LLM反思: {'启用' if validation_mgr.is_llm_reflection_enabled() else '禁用'}")

    # 显示参数限制
    logger.info(f"  ✅ 参数限制:")
    logger.info(f"     - 最大子问题数: {limits_mgr.get_max_sub_questions()}")
    logger.info(f"     - 最大证据字符数: {limits_mgr.get_max_evidence_chars()}")
    logger.info(f"     - 最大提案字符数: {limits_mgr.get_max_proposal_chars()}")

    # 步骤2: 初始化LLM模型(阶段4: 多模型解耦, 按角色从 models.yaml 路由)
    logger.info("🤖 [2/7] 初始化大语言模型...")
    _dashscope_key = os.getenv("DASHSCOPE_API_KEY")

    if not _dashscope_key:
        logger.error("  ❌ 错误: DASHSCOPE_API_KEY 未设置")
        raise ValueError("DASHSCOPE_API_KEY 环境变量未设置")

    logger.info("  ✅ API密钥: 已配置（日志中隐藏）")

    # LLM 用量跟踪(真实 token_usage → 成本估算看板)
    usage_handler = UsageCallbackHandler()

    # 多模型路由器: main(主推理) / fast(质控) / turbo(轻量) / consensus(主持人)
    # 型号可通过 MODEL_MAIN / MODEL_FAST / MODEL_TURBO / MODEL_CONSENSUS 环境变量覆盖
    router = ModelRouter(usage_handler=usage_handler)
    llm_max = router.get_llm("main")
    llm_plus = router.get_llm("fast")
    llm_turbo = router.get_llm("turbo")
    llm_consensus = router.get_llm("consensus")
    logger.info(f"  ✅ 模型加载完成: {router.describe()}")
    resources["model_router"] = router

    # 步骤3: 初始化上下文摘要服务
    logger.info("💬 [3/7] 初始化上下文摘要服务...")
    context_summary = ConversationSummaryService(
        llm=llm_turbo,
        prompt_manager=prompt_mgr
    )
    logger.info("  ✅ 上下文摘要服务初始化完成")

    # 步骤4: 初始化检索引擎
    logger.info("🔍 [4/7] 初始化向量检索引擎...")
    retriever = UnifiedSearchEngine(
        persist_dir=CONFIG.get("persist_dir", "./chroma_db_unified"),
        top_k=CONFIG.get("top_k_final", 3)
    )

    if retriever.chunks:
        _loaded_doc_names = sorted(set(
            chunk.metadata["source"].removesuffix(".pdf").removesuffix(".PDF")
            for chunk in retriever.chunks
            if chunk.metadata.get("source")
        ))
        report_mgr.update_doc_list(_loaded_doc_names)
        logger.info(f"  ✅ 检索引擎初始化完成")
        logger.info(f"     - 向量库路径: {CONFIG.get('persist_dir', './chroma_db_unified')}")
        logger.info(f"     - 文档数量: {len(retriever.chunks)} 个片段")
        logger.info(f"     - 文献数量: {len(_loaded_doc_names)} 篇")
        logger.info(f"     - 检索Top-K: {CONFIG.get('top_k_final', 3)}")
    else:
        logger.warning("  ⚠️  本地文档为空，system_role 使用 YAML 静态列表")

    # 步骤5: 初始化医疗助手
    logger.info("👨‍⚕️  [5/7] 初始化医疗助手...")
    medical_assistant = MedicalAssistant(
        llm_main=llm_max,
        llm_fast=llm_plus,
        retriever=retriever,
        prompt_manager=prompt_mgr,
        report_manager=report_mgr
    )
    logger.info("  ✅ 医疗助手初始化完成")

    # 步骤6: 初始化智能体
    logger.info("🧠 [6/7] 初始化临床推理智能体...")
    agent = QwenAgent(
        llm_proposer=llm_max,
        llm_critic=llm_plus,
        medical_assistant=medical_assistant,
        prompt_manager=prompt_mgr,
        report_manager=report_mgr,
        llm_turbo=llm_turbo,
        llm_consensus=llm_consensus,
        checkpointer=checkpointer,
    )
    logger.info("  ✅ 临床推理智能体初始化完成")

    # 步骤7: 初始化其他服务
    logger.info("🔧 [7/7] 初始化其他服务...")
    vision_service = VisionAnalysisService(prompt_manager=prompt_mgr)
    naming_model = NamingModel(llm=llm_turbo)
    logger.info("  ✅ 影像识别服务初始化完成")
    logger.info("  ✅ 命名模型初始化完成")

    # 统计初始化时间
    init_time = time.time() - start_time
    logger.info("=" * 80)
    logger.info(f"🎉 系统初始化完成！耗时: {init_time:.2f}秒")
    logger.info("=" * 80)

    return agent, naming_model, context_summary, vision_service, llm_turbo, retriever


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.info(">>> 正在初始化资源及加载模型...")
    resources["executor"] = concurrent.futures.ThreadPoolExecutor(max_workers=10)
    # 阶段7: 请求并发闸(单用户/全局), 防滥用拖垮模型服务
    resources["request_guard"] = RequestConcurrencyGuard(
        per_user_limit=int(os.getenv("MODEL_MAX_CONCURRENT_PER_USER", "2") or "2"),
        global_limit=int(os.getenv("MODEL_MAX_CONCURRENT_GLOBAL", "8") or "8"),
    )
    loop = asyncio.get_running_loop()

    try:
        # 阶段3: 检查点存储必须在应用主事件循环内创建(aiosqlite 连接绑定事件循环)
        checkpointer = await open_checkpointer()
        agent, naming, context_summary, vision_service, llm_turbo, retriever = await loop.run_in_executor(
            resources["executor"], init_all_resources, checkpointer
        )
        resources["model"] = agent
        resources["naming_model"] = naming
        resources["context_summary"] = context_summary
        resources["vision_service"] = vision_service
        resources["llm_turbo"] = llm_turbo
        resources["retriever"] = retriever
        resources["started_at"] = time.time()
        logging.info(">>> 所有模型组装完成，服务已就绪")
    except Exception as e:
        logging.error(f"!!! 模型初始化严重失败: {e}")
        import traceback
        logging.error(traceback.format_exc())
        raise

    yield

    logging.info("<<< 正在释放资源...")
    if resources["executor"]:
        resources["executor"].shutdown()
