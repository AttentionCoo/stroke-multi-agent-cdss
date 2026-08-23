"""API 请求/响应模型(从 main.py 拆出)。"""

from typing import List

from pydantic import BaseModel, Field


# 临床推理流入口请求体(/model/get_result): 问题 + 历史上下文 + 影像 + 报告/HITL 开关
class QueryRequest(BaseModel):
    question: str = Field(max_length=20000, description="患者问题(阶段7: 上限2万字符)")
    # round: 多专家推理反思轮数(默认 2 轮)
    round: int = 2
    all_info: str = Field(default="", max_length=100000, description="历史上下文(上限10万字符)")
    patient_id: int | None = None
    # patient_memory: 结构化记忆(短时/长时), 影像分析优先取其中的 short_term
    patient_memory: dict[str, str] = Field(default_factory=dict)
    # token: JWT, verify_token 校验后取用户 id(并发闸/审计)
    token: str
    # report_mode: 报告模板模式(默认 emergency), 映射报告管理器中的模板
    report_mode: str = "emergency"
    # show_thinking: 是否在 SSE 流中返回各节点思考过程
    show_thinking: bool = True
    images: list[str] = Field(default_factory=list, max_length=5, description="影像base64(最多5张)")
    human_review: bool = Field(default=False, description="阶段3 HITL: 报告生成前挂起等待医生复核")


# HITL 复核续跑请求体(/model/resume): 医生对挂起的会诊结论批准或驳回
class ReviewResumeRequest(BaseModel):
    token: str
    thread_id: str = Field(description="human_review 事件返回的 thread_id")
    approved: bool = Field(default=False, description="医生是否批准会诊结论")
    feedback: str = Field(default="", description="驳回时的修改意见, 反馈给专家重新会诊")


# /ai/analyze 健康风险分析请求体
class AnalyzeRequest(BaseModel):
    patientId: int
    data: str = Field(..., min_length=1)


# 健康风险分析结果(风险等级/建议/详情)
class AnalyzeResult(BaseModel):
    riskLevel: str
    suggestion: str
    analysisDetails: str


# /ai/analyze 统一响应包装 {code, msg, data}
class AnalyzeResponse(BaseModel):
    code: int
    msg: str
    data: AnalyzeResult


# /ai/quick-analyze 快速 AI 意见请求体(跳过多专家推理)
class QuickAnalyzeRequest(BaseModel):
    question: str = Field(..., min_length=1)
    token: str


# 快速意见结果(意见/关键点/风险等级)
class QuickAnalyzeResult(BaseModel):
    quickOpinion: str
    keyPoints: list[str]
    riskLevel: str


# /ai/quick-analyze 统一响应包装
class QuickAnalyzeResponse(BaseModel):
    code: int
    msg: str
    data: QuickAnalyzeResult


# /model/pubmed/search 文献检索请求体
class PubMedSearchRequest(BaseModel):
    query: str
    max_results: int = 5


# /model/tools/call 医疗工具调用请求体
class ToolCallRequest(BaseModel):
    name: str = Field(description="工具名称,如 nihss_score")
    arguments: dict = Field(default_factory=dict, description="工具参数 dict")
    token: str = Field(default="", description="JWT 鉴权令牌(与 /model/get_result 一致)")


# /model/lab_extract 化验单解析请求体(绿道表单自动回填)
class LabExtractRequest(BaseModel):
    token: str = Field(description="JWT 鉴权令牌")
    images: List[str] = Field(description="Base64 化验单图片列表(最多3张)")


# /model/kb/upload 知识库上传请求体
class KbUploadRequest(BaseModel):
    token: str = Field(description="JWT 鉴权令牌")
    files: List[dict] = Field(description="[{name, base64}] PDF 文件列表")


def _validate_kb_files(files: List[dict]) -> None:
    """知识库上传防护(阶段7): 单文件 base64 ≤ 20MB, 最多 10 个。"""
    from fastapi import HTTPException
    if len(files) > 10:
        raise HTTPException(status_code=413, detail="单次最多上传 10 个文件")
    for f in files:
        if len(str(f.get("base64", "") or "")) > 28_000_000:  # base64 约 20MB PDF
            raise HTTPException(status_code=413, detail=f"文件 {f.get('name', '')} 超过 20MB 限制")
