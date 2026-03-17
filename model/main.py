# main.py

import logging
import sys
import asyncio
import concurrent.futures
import itertools
from contextlib import asynccontextmanager
import os
import json
import jwt

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
import uvicorn

from Agent.qwen.qwen_agent import qwenAgent
from Agent.qwen.qwen_assistant import MedicalAssistant
from utils.naming_model import NamingModel
from makeData.Retrieve import UnifiedSearchEngine, CONFIG
from config.config_loader import get_prompt_manager, get_report_manager

from langchain_community.chat_models import ChatTongyi
from utils.context_summary import ConversationSummaryService
from error_codes import build_error_event, format_error_log

# 队列事件优先级映射：数字越小越优先，确保 error/done 能快速排到队首被消费
# heartbeat 直接 yield 不经过队列，此处仅作完整性定义
_QUEUE_PRIORITY = {
    "error":     0,
    "done":      1,
    "meta":      2,
    "result":    3,
    "thinking":  4,
    "heartbeat": 5,
}

os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-here")
ALGORITHM = "HS256"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

resources = {"model": None, "naming_model": None, "executor": None, "context_summary": None}


class QueryRequest(BaseModel):
    question: str
    round: int = 2
    all_info: str = ""
    token: str
    report_mode: str = "emergency"
    show_thinking: bool = True  # 是否输出中间思考过程


class AnalyzeRequest(BaseModel):
    patientId: int
    data: str = Field(..., min_length=1)
    all_info: str = ""
    token: str


class AnalyzeResult(BaseModel):
    riskLevel: str
    suggestion: str
    analysisDetails: str


class AnalyzeResponse(BaseModel):
    code: int
    msg: str
    data: AnalyzeResult


def init_all_resources():
    logging.info(">>> 开始组装模型依赖链...")

    prompt_mgr = get_prompt_manager()
    report_mgr = get_report_manager()
    logging.info(f">>> 可用报告模式: {report_mgr.list_modes()}")

    llm_max = ChatTongyi(model_name="qwen-max")
    llm_plus = ChatTongyi(model_name="qwen-plus")
    context_summary = ConversationSummaryService(
        llm=llm_plus,
        prompt_manager=prompt_mgr
    )

    retriever = UnifiedSearchEngine(
        persist_dir=CONFIG.get("persist_dir", "./chroma_db_unified"),
        top_k=CONFIG.get("top_k_final", 3)
    )

    medical_assistant = MedicalAssistant(
        llm_main=llm_max,
        llm_fast=llm_plus,
        retriever=retriever,
        prompt_manager=prompt_mgr,
        report_manager=report_mgr
    )

    agent = qwenAgent(
        llm_proposer=llm_max,
        llm_critic=llm_plus,
        medical_assistant=medical_assistant,
        prompt_manager=prompt_mgr,
        report_manager=report_mgr
    )

    naming_model = NamingModel()
    return agent, naming_model, context_summary


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.info(">>> 正在初始化资源及加载模型...")
    resources["executor"] = concurrent.futures.ThreadPoolExecutor(max_workers=10)
    loop = asyncio.get_running_loop()

    try:
        agent, naming, context_summary = await loop.run_in_executor(
            resources["executor"], init_all_resources
        )
        resources["model"] = agent
        resources["naming_model"] = naming
        resources["context_summary"] = context_summary
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


app = FastAPI(lifespan=lifespan)


def verify_token(token: str):
    try:
        jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")


@app.post("/model/get_result")
async def get_model_result(request: QueryRequest):
    verify_token(request.token)

    if not resources["model"]:
        raise HTTPException(status_code=503, detail="Model service not ready")

    async def generate():
        try:
            logging.info(f"=== 开始处理请求 ===")
            logging.info(f"请求问题: {request.question}")
            logging.info(f"请求all_info: {request.all_info}")
            logging.info(f"请求report_mode: {request.report_mode}")
            logging.info(f"请求show_thinking: {request.show_thinking}")

            loop = asyncio.get_running_loop()
            # 有界优先级队列，maxsize=50 防止推理速度远超消费速度时内存无限增长
            stream_queue = asyncio.PriorityQueue(maxsize=50)
            # 单调递增序列号：仅在事件循环线程中调用，防止同优先级元素比较 dict 时 TypeError
            seq_counter = itertools.count()
            final_answer_parts = []

            def _item_priority(item) -> int:
                """根据事件 type 字段查找优先级，None 哨兵按 done 级别处理"""
                if item is None:
                    return _QUEUE_PRIORITY["done"]
                if isinstance(item, dict):
                    return _QUEUE_PRIORITY.get(item.get("type", ""), 3)
                return 3

            async def enqueue(item, *, droppable: bool = False):
                """
                将事件放入优先级队列，元组格式 (priority, seq, item)。
                droppable=True（thinking）：超时 30s 后丢弃，打印 warning。
                droppable=False（error/done/meta/result）：永久阻塞等待，绝不丢弃。
                """
                priority = _item_priority(item)
                seq = next(seq_counter)
                entry = (priority, seq, item)
                if droppable:
                    try:
                        await asyncio.wait_for(stream_queue.put(entry), timeout=30.0)
                    except asyncio.TimeoutError:
                        event_type = item.get("type", "unknown") if isinstance(item, dict) else "sentinel"
                        logging.warning(f"队列已满超时 30s，丢弃低优先级事件: type={event_type}")
                else:
                    # error/done/meta/result：阻塞等待空位，不受超时限制
                    await stream_queue.put(entry)

            def run_stream_in_thread():
                try:
                    for chunk in resources["model"].run_clinical_reasoning(
                        case_text=request.question,
                        all_info=request.all_info,
                        report_mode=request.report_mode,
                        show_thinking=request.show_thinking
                    ):
                        # thinking 事件可丢弃，其余事件不可丢弃
                        chunk_type = chunk.get("type", "") if isinstance(chunk, dict) else ""
                        droppable = chunk_type == "thinking"
                        asyncio.run_coroutine_threadsafe(
                            enqueue(chunk, droppable=droppable), loop
                        )
                except Exception as e:
                    # 记录含完整堆栈的错误日志
                    logging.error(f"模型流式生成出错 | {format_error_log(e)}")
                    # error 事件不可丢弃
                    asyncio.run_coroutine_threadsafe(
                        enqueue(build_error_event(e, talk_id=None), droppable=False), loop
                    )
                finally:
                    # None 哨兵（done 信号）不可丢弃
                    asyncio.run_coroutine_threadsafe(
                        enqueue(None, droppable=False), loop
                    )

            loop.run_in_executor(resources["executor"], run_stream_in_thread)

            naming_future = None
            if not request.all_info:
                naming_future = loop.run_in_executor(
                    resources["executor"],
                    resources["naming_model"].run_naming,
                    request.question
                )

            generated_name = None
            while True:
                # 等待队列数据，超时 10s 则发送心跳 comment 保活连接，不终止循环
                # 解包优先级元组 (priority, seq, item)，priority/seq 仅用于队列排序，消费时丢弃
                try:
                    _, _, item = await asyncio.wait_for(stream_queue.get(), timeout=10.0)
                except asyncio.TimeoutError:
                    logging.debug("Queue 空闲超时，发送 SSE 心跳事件")
                    yield json.dumps({"type": "heartbeat", "talkId": None}, ensure_ascii=False) + "\n"
                    continue

                if item is None:
                    if not generated_name and resources.get("naming_model"):
                        try:
                            generated_name = await loop.run_in_executor(
                                resources["executor"],
                                resources["naming_model"].run_naming,
                                request.question
                            )
                        except Exception:
                            generated_name = "咨询"

                    answer_text = "".join(final_answer_parts).strip()
                    updated_summary = request.all_info
                    summary_meta = {
                        "score": 0.0,
                        "is_valuable": False,
                        "reason": "no final answer",
                        "summary": updated_summary,
                        "all_info": updated_summary
                    }

                    if answer_text and resources.get("context_summary"):
                        try:
                            summary_result = await loop.run_in_executor(
                                resources["executor"],
                                resources["context_summary"].update_all_info,
                                request.all_info,
                                request.question,
                                answer_text,
                                0.4
                            )
                            updated_summary = summary_result.get("updated_all_info", request.all_info)
                            summary_meta = {
                                "score": summary_result.get("score", 0.0),
                                "is_valuable": summary_result.get("is_valuable", False),
                                "reason": summary_result.get("reason", ""),
                                "summary": updated_summary,
                                "all_info": updated_summary
                            }
                        except Exception as summary_error:
                            logging.error(f"all_info 更新失败: {summary_error}")
                            summary_meta["reason"] = f"summary failed: {summary_error}"

                    final_name = generated_name or "咨询"
                    summary_meta["name"] = final_name

                    # 标准格式：meta 事件携带 all_info 更新信息
                    yield json.dumps({"type": "meta", "content": {"all_info_update": summary_meta}}, ensure_ascii=False) + "\n"
                    # done 事件：标志流结束，携带汇总信息
                    yield json.dumps({
                        "type": "done",
                        "content": "",
                        "result": answer_text,
                        "summary": updated_summary,
                        "name": final_name,
                        "all_info": updated_summary
                    }, ensure_ascii=False) + "\n"
                    break

                if isinstance(item, dict) and item.get("type") == "error":
                    # 透传完整结构化错误事件（含 error 对象和双写的 content 字段）
                    yield json.dumps(item, ensure_ascii=False) + "\n"
                    break

                if naming_future and naming_future.done() and not generated_name:
                    try:
                        generated_name = naming_future.result()
                    except Exception:
                        generated_name = "咨询"

                chunk_type = item.get("type", "") if isinstance(item, dict) else ""

                # 直接透传 Agent 标准格式事件
                if chunk_type == "result":
                    content = item["content"]
                    if hasattr(content, "content"):
                        content = content.content
                    content_str = str(content)
                    final_answer_parts.append(content_str)
                    yield json.dumps({"type": "result", "content": content_str}, ensure_ascii=False) + "\n"

                elif chunk_type == "thinking":
                    yield json.dumps({
                        "type": "thinking",
                        "step": item.get("step", ""),
                        "title": item.get("title", ""),
                        "content": str(item.get("content", ""))
                    }, ensure_ascii=False) + "\n"

                elif chunk_type == "meta":
                    yield json.dumps({"type": "meta", "content": item["content"]}, ensure_ascii=False) + "\n"

        except Exception as e:
            # 记录含完整堆栈的错误日志
            logging.error(f"generate() 外层异常 | {format_error_log(e)}")
            # 构造结构化错误事件并 yield（双写 content 字段保持旧前端兼容）
            yield json.dumps(build_error_event(e, talk_id=None), ensure_ascii=False) + "\n"

    return StreamingResponse(
        generate(),
        media_type="text/plain",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*"
        }
    )


@app.post("/ai/analyze", response_model=AnalyzeResponse)
async def analyze_patient_health_risk(request: AnalyzeRequest):
    verify_token(request.token)

    if not resources["model"]:
        raise HTTPException(status_code=503, detail="Model service not ready")

    patient_text = request.data.strip()
    if not patient_text:
        raise HTTPException(status_code=422, detail="data cannot be empty")

    logging.info("=== 开始健康风险分析请求 ===")
    logging.info(f"patientId: {request.patientId}")
    logging.info(f"data: {patient_text[:200]}")
    logging.info(f"all_info: {request.all_info[:200] if request.all_info else ''}")

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        resources["executor"],
        resources["model"].analyze_patient_risk,
        patient_text,
        request.all_info
    )

    return {
        "code": 1,
        "msg": "success",
        "data": result
    }


@app.post("/admin/reload_config")
async def reload_config():
    try:
        get_prompt_manager().reload()
        get_report_manager().reload()
        return {"status": "ok", "message": "配置已热更新"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/admin/report_modes")
async def list_report_modes():
    mgr = get_report_manager()
    modes = mgr.list_modes()
    return {
        "modes": [
            {"key": m, "name": mgr.get_template_name(m)}
            for m in modes
        ]
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)