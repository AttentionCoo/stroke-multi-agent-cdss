"""阶段3 结构化输出 Schema。

关键节点(intent / evidence_router / research_plan)用 Pydantic 约束 LLM 输出,
配合 llm.with_structured_output() 消除"输出 JSON → 手写解析"的脆弱性。

设计原则:
- 硬路由字段用 Literal 严格校验(intent type), 校验失败自动回退文本解析路径;
- 其余字段保持宽松(evidence_type 等由节点内的 normalize 逻辑统一兜底);
- 所有字段带默认值, 模型漏字段不导致整体失败。
"""

from typing import Dict, List, Literal

from pydantic import BaseModel, Field


class IntentResult(BaseModel):
    """意图分类结果: consultation(问诊) / knowledge(知识问答) / irrelevant(无关)。"""

    type: Literal["consultation", "knowledge", "irrelevant"] = Field(
        description="输入意图类型, 必须为三者之一"
    )
    reason: str = Field(default="", description="简要判断原因")


class EvidenceRoute(BaseModel):
    """单个检索查询的证据路由决策。"""

    query: str = Field(description="原检索查询, 必须与输入完全一致")
    evidence_type: str = Field(
        default="treatment",
        description="treatment/diagnosis/anatomy/etiology/prognosis/prevention",
    )
    target_categories: List[str] = Field(
        default_factory=list, description="目标知识类别: 指南/专家共识/规范/教材/其他"
    )
    keywords: List[str] = Field(
        default_factory=list, description="2-4 个医学标准检索关键词"
    )


class EvidenceRoutes(BaseModel):
    """Evidence Router 输出: 每个查询一条路由。"""

    routes: List[EvidenceRoute] = Field(default_factory=list)


class DecisionItem(BaseModel):
    """临床决策节点(Decision Planner 核心输出)。"""

    decision_id: str = ""
    decision_name: str
    decision_type: str = "treatment"
    patient_evidence: List[str] = Field(default_factory=list)
    uncertainty: List[str] = Field(default_factory=list)
    required_evidence: List[str] = Field(default_factory=list)
    # 空串 → 节点 normalize 逻辑回退到 decision_type(保持既有语义)
    evidence_type: str = ""
    evidence_source: List[str] = Field(default_factory=list)
    priority: int = 5
    pico: Dict = Field(default_factory=dict)
    search_query: List[str] = Field(default_factory=list)


class RetrievalTask(BaseModel):
    """面向临床决策的检索任务。"""

    question: str = ""
    query: str


class ResearchPlanResult(BaseModel):
    """决策规划输出。"""

    need_retrieve: bool = True
    missing_information: List[str] = Field(default_factory=list)
    clinical_decisions: List[DecisionItem] = Field(default_factory=list)
    retrieval_tasks: List[RetrievalTask] = Field(default_factory=list)
    expanded_queries: List[str] = Field(default_factory=list)
    hypothetical_document: str = ""


class HumanReviewDecision(BaseModel):
    """医生复核决定(HITL resume 载荷)。"""

    approved: bool = Field(description="是否批准会诊结论")
    feedback: str = Field(default="", description="驳回时的修改意见, 会反馈给专家重新会诊")
