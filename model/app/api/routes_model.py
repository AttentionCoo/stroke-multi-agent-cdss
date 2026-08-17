"""/model/* 路由(从 main.py 拆出): 临床推理流、HITL 续跑、知识库管理、运行时信息、工具与检索。"""

import asyncio
import json
import logging
import os
import time
import uuid

from fastapi import APIRouter, HTTPException, Header
from sse_starlette.sse import EventSourceResponse

from app.runtime import resources, verify_token, start_kb_job
from app.api.models import (
    QueryRequest,
    ReviewResumeRequest,
    ToolCallRequest,
    LabExtractRequest,
    KbUploadRequest,
    PubMedSearchRequest,
    _validate_kb_files,
)
from app.agents.tools.registry import call_tool, get_tool_schemas, TOOL_GROUPS
from app.services.pubmed_service import PubMedService
from app.utils.error_codes import build_error_event
from app.utils.security import mask_sensitive
from app.utils.usage import begin_request, end_request

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/model", tags=["model"])


@router.post("/get_result")
async def get_model_result(request: QueryRequest):
    """临床推理接口 - 增强日志版本"""
    payload = verify_token(request.token)
    uid = str(payload.get("id", "anon"))

    if not resources["model"]:
        raise HTTPException(status_code=503, detail="Model service not ready")

    # 阶段7: 并发闸(单用户/全局上限), 超限直接 429, 不进入流
    guard = resources.get("request_guard")
    if guard is not None and not guard.try_acquire(uid):
        raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")

    async def generate():
        req_id = uuid.uuid4().hex[:12]
        start_time = time.time()
        # 本请求的 LLM 用量账本(contextvars 隔离)
        begin_request()

        try:
            logger.info("=" * 80)
            logger.info(f"🔵 [请求 {req_id}] 开始处理临床推理请求")
            logger.info("=" * 80)
            logger.info(f"📝 问题内容(脱敏): {mask_sensitive(request.question)[:200]}")
            logger.info(f"🎯 报告模式: {request.report_mode}")
            logger.info(f"🖼️  影像数量: {len(request.images)}")
            logger.info(f"💬 历史信息: {len(request.all_info) if request.all_info else 0} 字符")
            logger.info(f"🔍 显示思考过程: {request.show_thinking}")
            logger.info("-" * 80)

            loop = asyncio.get_running_loop()
            final_answer_parts = []
            node_start_time = {}
            node_count = 0

            if request.images:
                logger.info(f"🖼️  [节点 {node_count + 1}] 影像分析开始")
                node_start_time["vision"] = time.time()
                vision_chunk_count = 0
                vision_status = "服务未就绪"

                vision_svc = resources.get("vision_service")
                if not vision_svc:
                    logger.warning("⚠️  影像识别服务未就绪")
                    yield json.dumps({"type": "token", "content": "影像识别服务未就绪，请稍后重试。"}, ensure_ascii=False)
                else:
                    vision_status = "已完成"
                    async for event in vision_svc.analyze_stream(
                        images=request.images,
                        question=request.question,
                        all_info=(
                            request.patient_memory.get("short_term", "")
                            if request.patient_memory
                            else request.all_info
                        ),
                    ):
                        if event.get("type") == "thinking":
                            logger.info(f"  🤔 影像分析思考: {event.get('title', '正在分析影像...')}")
                            yield json.dumps({
                                "type": "node_start",
                                "node": "vision",
                                "label": event.get("title", "正在分析影像..."),
                                "content": event.get("content", ""),
                                "status": "running",
                            }, ensure_ascii=False)
                        elif event.get("type") == "chunk":
                            content_str = str(event.get("content", ""))
                            if event.get("failed"):
                                vision_status = "分析失败"
                            if content_str:
                                final_answer_parts.append(content_str)
                                vision_chunk_count += 1
                                yield json.dumps({"type": "token", "content": content_str}, ensure_ascii=False)

                vision_time = time.time() - node_start_time["vision"]
                logger.info(f"✅ 影像分析完成 - 耗时: {vision_time:.2f}秒, 生成: {vision_chunk_count} 个片段")

                answer_text = "".join(final_answer_parts).strip()
                total_time = time.time() - start_time

                yield json.dumps({
                    "type": "node_done",
                    "node": "vision",
                    "label": "影像分析",
                    "summary": json.dumps({
                        "分析状态": vision_status,
                        "输出片段数": vision_chunk_count,
                        "结果长度": f"{len(answer_text)} 字符",
                    }, ensure_ascii=False, separators=(",", ":")),
                    "status": "done",
                }, ensure_ascii=False)

                yield json.dumps({
                    "type": "done",
                    "request_id": req_id,
                    "name": "影像分析",
                    "all_info": request.all_info,
                    "usage": end_request(),
                }, ensure_ascii=False)

                logger.info(f"🟢 [请求 {req_id}] 完成 - 总耗时: {total_time:.2f}秒")
                logger.info("=" * 80)
                return

            naming_future = None
            if not request.all_info and resources.get("naming_model"):
                logger.info(f"🏷️  [节点 {node_count + 1}] 命名模型将在推理完成后执行")
                node_start_time["naming"] = time.time()

            logger.info(f"🧠 [节点 {node_count + 1}] 临床推理链开始")
            node_start_time["clinical_reasoning"] = time.time()

            current_node = None
            node_chunk_counts = {}
            review_pending = False
            review_thread_id = None

            async for event in resources["model"].run_clinical_reasoning(
                case_text=request.question,
                all_info=request.all_info,
                patient_memory=request.patient_memory,
                report_mode=request.report_mode,
                show_thinking=request.show_thinking,
                human_review=request.human_review,
            ):
                if not isinstance(event, dict):
                    continue

                if event.get("type") == "error":
                    logger.error(f"❌ 推理错误: {event.get('content', 'Unknown error')}")
                    yield json.dumps(event, ensure_ascii=False)
                    return

                if event.get("type") == "human_review":
                    # HITL: 推理挂起等待医生复核, 记录 thread_id 供 /model/resume 续跑
                    review_pending = True
                    review_thread_id = event.get("thread_id")

                if event.get("type") == "node_start":
                    node_count += 1
                    current_node = event.get("node")
                    node_label = event.get("label", "")
                    logger.info(f"  🔄 [节点 {node_count}] {current_node}: {node_label}")
                    node_chunk_counts[current_node] = 0

                if event.get("type") == "token":
                    content_str = str(event.get("content", ""))
                    if content_str:
                        final_answer_parts.append(content_str)
                        if current_node:
                            node_chunk_counts[current_node] = node_chunk_counts.get(current_node, 0) + 1

                yield json.dumps(event, ensure_ascii=False)

            reasoning_time = time.time() - node_start_time["clinical_reasoning"]
            logger.info(f"✅ 临床推理链完成 - 耗时: {reasoning_time:.2f}秒")

            if review_pending:
                # 挂起: 不生成答案/摘要/命名, 等待医生复核后由 /model/resume 续跑
                logger.info(f"⏸️  [请求 {req_id}] HITL 挂起, 等待医生复核 (thread_id={review_thread_id})")
                yield json.dumps({
                    "type": "done",
                    "request_id": req_id,
                    "name": None,
                    "all_info": request.all_info,
                    "status": "human_review_pending",
                    "thread_id": review_thread_id,
                    "usage": end_request(),
                }, ensure_ascii=False)
                return

            answer_text = "".join(final_answer_parts).strip()

            generated_name = "咨询"
            if naming_future is None and not request.all_info and resources.get("naming_model"):
                # 推理完成后基于问题+回答生成标题(更准确)
                logger.info(f"🏷️  [节点 {node_count + 1}] 命名模型推理开始(基于问题+回答)")
                node_start_time["naming"] = time.time()
                # copy_context().run: 线程池执行时保留请求的 contextvars(LLM 用量账本)
                naming_future = loop.run_in_executor(
                    resources["executor"],
                    __import__("contextvars").copy_context().run,
                    resources["naming_model"].run_naming,
                    request.question,
                    answer_text[:500],
                )
            if naming_future:
                try:
                    generated_name = await naming_future or "咨询"
                    naming_time = time.time() - node_start_time["naming"]
                    logger.info(f"✅ 命名推理完成 - 耗时: {naming_time:.2f}秒, 结果: {generated_name}")
                except Exception as e:
                    logger.warning(f"⚠️  命名推理失败: {e}")

            updated_all_info = request.all_info

            if answer_text and resources.get("context_summary"):
                logger.info(f"💬 [节点 {node_count + 1}] 上下文摘要更新开始")
                summary_start = time.time()
                try:
                    # copy_context().run: 线程池执行时保留请求的 contextvars(LLM 用量账本)
                    summary_result = await loop.run_in_executor(
                        resources["executor"],
                        __import__("contextvars").copy_context().run,
                        resources["context_summary"].update_all_info,
                        request.all_info,
                        request.question,
                        answer_text,
                        0.4,
                    )
                    updated_all_info = summary_result.get("updated_all_info", request.all_info)
                    summary_time = time.time() - summary_start
                    logger.info(f"✅ 上下文摘要更新完成 - 耗时: {summary_time:.2f}秒")
                    logger.info(f"     原始长度: {len(request.all_info)} 字符")
                    logger.info(f"     更新长度: {len(updated_all_info)} 字符")
                except Exception as summary_error:
                    logger.error(f"❌ 上下文摘要更新失败: {summary_error}")

            total_time = time.time() - start_time
            logger.info("-" * 80)
            logger.info(f"📊 [请求 {req_id}] 性能统计:")
            logger.info(f"     总耗时: {total_time:.2f}秒")
            logger.info(f"     生成文本: {len(answer_text)} 字符")
            logger.info(f"     平均速度: {len(answer_text)/total_time:.1f} 字符/秒")
            logger.info(f"     咨询名称: {generated_name}")
            logger.info("-" * 80)
            logger.info(f"🟢 [请求 {req_id}] 请求处理完成")
            logger.info("=" * 80)

            usage_summary = end_request()
            logger.info(f"💰 [请求 {req_id}] LLM 用量: {usage_summary['input_tokens']}入/{usage_summary['output_tokens']}出 tokens, "
                         f"{usage_summary['calls']}次调用, 估算成本 ¥{usage_summary['cost']}")

            yield json.dumps({
                "type": "done",
                "request_id": req_id,
                "name": generated_name,
                "all_info": updated_all_info,
                "usage": usage_summary,
            }, ensure_ascii=False)

        except Exception as e:
            end_request()
            error_time = time.time() - start_time
            logger.error(f"❌ [请求 {req_id}] 处理失败 - 耗时: {error_time:.2f}秒")
            logger.error(f"     错误类型: {type(e).__name__}")
            logger.error(f"     错误信息: {str(e)}")
            logger.error("=" * 80)
            yield json.dumps(build_error_event(e, talk_id=None), ensure_ascii=False)
        finally:
            if guard is not None:
                guard.release(uid)

    return EventSourceResponse(generate(), ping=15)


@router.post("/resume")
async def resume_model_result(request: ReviewResumeRequest):
    """HITL 复核续跑接口(阶段3) - 医生对挂起的会诊结论做出决定后恢复推理流。

    请求体: {token, thread_id, approved, feedback}
    - approved=True  → 继续生成最终报告;
    - approved=False → 医生意见反馈给专家重新会诊(可能再次挂起等待复核)。
    """
    verify_token(request.token)

    if not resources["model"]:
        raise HTTPException(status_code=503, detail="Model service not ready")

    async def generate():
        req_id = uuid.uuid4().hex[:12]
        start_time = time.time()
        begin_request()
        final_answer_parts = []
        review_pending = False
        try:
            logger.info(f"▶️  [请求 {req_id}] HITL 续跑开始 (thread_id={request.thread_id[:12]}..., "
                        f"approved={request.approved})")

            async for event in resources["model"].resume_clinical_reasoning(
                request.thread_id,
                {"approved": request.approved, "feedback": request.feedback},
            ):
                if not isinstance(event, dict):
                    continue
                if event.get("type") == "error":
                    logger.error(f"❌ 续跑错误: {event.get('content', 'Unknown error')}")
                    yield json.dumps(event, ensure_ascii=False)
                    return
                if event.get("type") == "human_review":
                    review_pending = True
                if event.get("type") == "token":
                    content_str = str(event.get("content", ""))
                    if content_str:
                        final_answer_parts.append(content_str)
                yield json.dumps(event, ensure_ascii=False)

            answer_text = "".join(final_answer_parts).strip()
            usage_summary = end_request()
            total_time = time.time() - start_time
            logger.info(f"✅ [请求 {req_id}] HITL 续跑完成 - 耗时: {total_time:.2f}秒, "
                        f"生成: {len(answer_text)} 字符, 状态: {'再次挂起' if review_pending else '完成'}")
            yield json.dumps({
                "type": "done",
                "request_id": req_id,
                "name": "咨询",
                "all_info": "",
                "status": "human_review_pending" if review_pending else "completed",
                "thread_id": request.thread_id if review_pending else None,
                "usage": usage_summary,
            }, ensure_ascii=False)
        except Exception as e:
            end_request()
            logger.error(f"❌ [请求 {req_id}] HITL 续跑失败: {e}")
            yield json.dumps(build_error_event(e, talk_id=None), ensure_ascii=False)

    return EventSourceResponse(generate(), ping=15)


# ============ 知识库管理(界面化) ============


@router.post("/kb/upload")
async def kb_upload(request: KbUploadRequest):
    """上传指南 PDF → 保存到文档目录 → 后台热更新知识库。"""
    verify_token(request.token)
    _validate_kb_files(request.files)
    retriever = resources.get("retriever")
    if not retriever:
        raise HTTPException(status_code=503, detail="Retriever not ready")
    import base64 as _b64

    os.makedirs(retriever.docs_dir, exist_ok=True)
    saved = []
    for f in request.files[:10]:
        name = os.path.basename(str(f.get("name", "") or "upload.pdf"))
        if not name.lower().endswith(".pdf"):
            name += ".pdf"
        data = _b64.b64decode(str(f.get("base64", "") or ""))
        if not data:
            continue
        with open(os.path.join(retriever.docs_dir, name), "wb") as fh:
            fh.write(data)
        saved.append(name)
    if not saved:
        return {"code": 0, "msg": "未收到有效文件", "data": None}
    job_id = start_kb_job("upload")
    return {"code": 1, "msg": "success", "data": {"saved": saved, "job_id": job_id}}


@router.delete("/kb/documents/{name}")
async def kb_delete_document(name: str, token: str = Header("")):
    """删除指南 PDF → 后台热更新知识库。"""
    verify_token(token)
    retriever = resources.get("retriever")
    if not retriever:
        raise HTTPException(status_code=503, detail="Retriever not ready")
    safe_name = os.path.basename(name)
    path = os.path.join(retriever.docs_dir, safe_name)
    if not os.path.exists(path):
        return {"code": 0, "msg": "文件不存在", "data": None}
    os.remove(path)
    job_id = start_kb_job("delete")
    return {"code": 1, "msg": "success", "data": {"deleted": safe_name, "job_id": job_id}}


@router.post("/kb/reload")
async def kb_reload(token: str = Header("")):
    """手动触发知识库热更新。"""
    verify_token(token)
    job_id = start_kb_job("reload")
    return {"code": 1, "msg": "success", "data": {"job_id": job_id}}


@router.get("/kb/status")
async def kb_status(token: str = Header("")):
    """知识库统计 + 最近任务状态。"""
    verify_token(token)
    retriever = resources.get("retriever")
    stats = retriever.stats() if retriever else {"documents": [], "document_count": 0, "chunk_count": 0, "collections": {}}
    from app.runtime import _KbJobs
    active = next((v for v in _KbJobs.values() if v.get("status") == "running"), None)
    return {"code": 1, "msg": "success", "data": {"stats": stats, "active_job": active}}


@router.get("/info")
async def model_info(token: str = Header("")):
    """运行时信息(阶段5): 多模型路由配置、检查点存储类型、知识库规模、运行时长。"""
    verify_token(token)
    router = resources.get("model_router")
    checkpointer = None
    if resources.get("model") is not None:
        graph = getattr(resources["model"], "graph", None)
        checkpointer = type(getattr(graph, "checkpointer", None)).__name__ if graph is not None else None
    retriever = resources.get("retriever")
    kb = retriever.stats() if retriever else {}
    uptime_s = int(time.time() - float(resources.get("started_at", time.time())))
    guard = resources.get("request_guard")
    return {
        "code": 1,
        "msg": "success",
        "data": {
            "models": router.info() if router else {},
            "checkpointer": checkpointer or "unknown",
            "kb": {
                "documents": kb.get("document_count", 0),
                "chunks": kb.get("chunk_count", 0),
                "health_warnings": kb.get("health_warnings", []),
            },
            "uptime_seconds": uptime_s,
            "in_flight_requests": guard.active() if guard else 0,
        },
    }


@router.post("/lab_extract")
async def extract_lab_fields_api(request: LabExtractRequest):
    """化验单拍照解析: 提取结构化字段供绿道表单自动回填。"""
    verify_token(request.token)
    vision_svc = resources.get("vision_service")
    if not vision_svc:
        raise HTTPException(status_code=503, detail="Vision service not ready")
    try:
        data = await asyncio.to_thread(vision_svc.extract_lab_fields, request.images[:3])
        return {"code": 1, "msg": "success", "data": data}
    except Exception as e:
        logger.warning(f"化验单解析失败: {e}")
        return {"code": 0, "msg": f"解析失败: {str(e)[:200]}", "data": None}


@router.get("/tools/list")
async def tools_list():
    """脑卒中医疗工具列表接口"""
    return {
        "code": 1,
        "msg": "success",
        "data": {
            "tools": get_tool_schemas(),
            "groups": TOOL_GROUPS,
            "count": len(get_tool_schemas()),
        },
    }


@router.post("/tools/call")
async def tools_call(request: ToolCallRequest):
    """脑卒中医疗工具调用接口"""
    if request.token:
        verify_token(request.token)

    result = call_tool(request.name, request.arguments)
    if not result.get("ok"):
        # 错误响应脱敏:不向外暴露内部异常细节
        raise HTTPException(
            status_code=400,
            detail={
                "ok": False,
                "tool": result.get("tool", ""),
                "error": result.get("error", "工具调用失败"),
                "available": result.get("available", []),
            },
        )
    return {"code": 1, "msg": "success", "data": result["result"]}


@router.post("/pubmed/search")
async def pubmed_search(request: PubMedSearchRequest):
    """PubMed文献检索接口 - 增强日志版本"""
    query = request.query.strip()
    if not query:
        logger.info("🔍 PubMed检索: 查询为空，返回空结果")
        return {"code": 1, "msg": "success", "data": {"papers": []}}

    start_time = time.time()
    req_id = uuid.uuid4().hex[:12]

    logger.info("=" * 80)
    logger.info(f"📚 [请求 {req_id}] 开始PubMed文献检索")
    logger.info("=" * 80)
    logger.info(f"🔍 查询关键词: {query}")
    logger.info(f"📊 最大结果数: {request.max_results}")
    logger.info("-" * 80)

    svc = PubMedService()
    try:
        papers = await svc.search_papers(query, max_results=request.max_results)
        search_time = time.time() - start_time

        logger.info(f"✅ PubMed检索完成 - 耗时: {search_time:.2f}秒")
        logger.info(f"📊 检索结果: {len(papers)} 篇文献")

        if papers:
            for i, paper in enumerate(papers[:3], 1):  # 只显示前3篇
                title = paper.get('title', 'Unknown')
                logger.info(f"     [{i}] {title[:60]}{'...' if len(title) > 60 else ''}")
            if len(papers) > 3:
                logger.info(f"     ... 还有 {len(papers) - 3} 篇文献")

        logger.info("-" * 80)
        logger.info(f"🟢 [请求 {req_id}] PubMed检索完成")
        logger.info("=" * 80)

    except Exception as e:
        error_time = time.time() - start_time
        logger.error(f"❌ [请求 {req_id}] PubMed检索失败 - 耗时: {error_time:.2f}秒")
        logger.error(f"     错误类型: {type(e).__name__}")
        logger.error(f"     错误信息: {str(e)}")
        logger.error("=" * 80)
        papers = []

    return {"code": 1, "msg": "success", "data": {"papers": papers}}
