"""统一数据模型"""
# 定义卒中 CDSS 的结构化临床上下文(ClinicalContext)与 LangGraph 共享状态(ClinicalState)，
# 后者是贯穿整个工作流的状态字典，各节点读写其中的字段。
from typing import List, Dict, Optional, Annotated
from pydantic import BaseModel, Field
from typing_extensions import TypedDict


# 结构化临床信息抽取结果：由病例结构化节点填写的患者信息容器，字段名即中文语义。
class ClinicalContext(BaseModel):
    """临床上下文"""
    基本信息: Dict = Field(default_factory=dict)
    起病方式: str = ""
    主要症状: List[str] = Field(default_factory=list)
    神经系统查体: Dict = Field(default_factory=dict)
    意识水平: str = ""
    生命体征: Dict = Field(default_factory=dict)
    既往史: List[str] = Field(default_factory=list)
    用药史: List[str] = Field(default_factory=list)
    危险因素: List[str] = Field(default_factory=list)
    非卒中线索: List[str] = Field(default_factory=list)


# LangGraph 共享状态字典：整个工作流各节点通过此 TypedDict 读写中间结果，
# 字段覆盖病例信息、检索、专家会诊、合规审计到最终报告的全链路数据。
class ClinicalState(TypedDict):
    """临床状态（用于 LangGraph）"""
    case_text: str
    all_info: str
    patient_memory: Dict[str, str]
    active_memory: str
    report_mode: str
    intent_type: str
    context: Dict
    clinical_questions: List[str]
    retrieval_tasks: List[Dict]
    retrieval_queries: List[str]
    retrieved_queries: List[str]
    hypothetical_document: str
    need_retrieve: bool
    evidence_quality: float
    evidence_assessment: str
    missing_information: List[str]
    retrieval_round: int
    key_risks: List[str]
    complexity: str
    evidence: str
    proposal: str
    critique: str
    user_questions: List[str]
    report: str
    
    # 新增：中层多智能体与后层校验需要的数据流转字段
    generalist_advice: str
    specialist_advice: str
    pharmacist_advice: str
    expert_opinions: Dict[str, str]
    debate_transcript: str
    consensus: str
    validation_passed: bool
    validation_feedback: str
    reflection_count: int

    # 新增：工具调用（tool calling）字段
    tool_results: str
    tool_calls: List[Dict]

    # 新增：临床决策规划（Clinical Decision Planner）
    clinical_decisions: List[Dict]

    # 新增：Evidence Router Agent 输出
    router_evidence_types: List[str]
    router_categories: List[List[str]]
    router_keywords: List[List[str]]
    router_routes: List[Dict]

    # 新增：HITL 人工复核(报告生成前可选医生审批, 阶段3)
    human_review_required: bool
    review_decision: Dict
    review_approved: bool
    review_feedback: str
    human_review_done: bool
    review_count: int

    # 新增：合规审计(validate 之后, PHI/绝对化断言/剂量 + 免责声明留痕)
    compliance_passed: bool
    compliance_issues: List[str]
    compliance_warnings: List[str]
    compliance_audit: Dict
