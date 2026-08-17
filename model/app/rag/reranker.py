"""BGE Rerank 重排器(从 retrievers.py 拆出, 单一职责)。

gte-rerank API 重排 + Medical Evidence Score 医学化加权,
API 不可用/限流时回退规则排序, 并标记降级链层级(rerank_layer)供质量看板追溯。
"""

import logging
import os
import time
from http import HTTPStatus
from typing import List

import dashscope
from dotenv import load_dotenv
from langchain_core.documents import Document

logger = logging.getLogger(__name__)


class BGEReranker:
    def __init__(self, top_k: int = 5):
        load_dotenv()
        self.api_key = os.getenv("DASHSCOPE_API_KEY")
        if not self.api_key:
            logger.warning("⚠️ 未找到 DASHSCOPE_API_KEY，Rerank 功能已禁用")
        self.top_k = top_k
        self.model = "gte-rerank"
        self.enabled = bool(self.api_key)  # 根据API密钥是否存在决定是否启用

    @staticmethod
    def _normalize_rrf_to_relevance(docs: List[Document]) -> List[Document]:
        """Rerank API 不可用时的回退: 将 RRF score 归一化为 relevance_score(0-1)。

        使 _apply_medical_score 的语义分项在无 API 时仍然有区分度。
        """
        scores = [float(d.metadata.get("rrf_score", 0.0) or 0.0) for d in docs]
        max_s = max(scores) if scores else 1.0
        if max_s <= 0:
            max_s = 1.0
        for d, s in zip(docs, scores):
            d.metadata["relevance_score"] = round(s / max_s, 4)
        return docs

    @staticmethod
    def _mark_layer(docs: List[Document], layer: str) -> None:
        """降级链标记: 记录本次重排实际使用的层级, 供检索质量看板/日志追溯。"""
        for d in docs:
            d.metadata["rerank_layer"] = layer

    def _fallback_medical_rank(self, docs: List[Document], query: str,
                               evidence_type: str | None,
                               actual_top_k: int) -> List[Document]:
        """Rerank 不可用时的回退: RRF 归一化 + Medical Evidence Score 规则排序。

        Medical Evidence Score 是纯规则加权(证据类型/权威/时效/主题/干预匹配),
        不依赖外部 API, 保证即使 gte-rerank 失败, 排序也不退化为纯 embedding 相似度。
        """
        self._normalize_rrf_to_relevance(docs)
        reranked = self._apply_medical_score(docs, query, evidence_type)
        self._mark_layer(reranked, "rule_fallback")
        logger.info(f"⚠️ 使用规则回退排序(无 Rerank API): {len(docs)} → {len(reranked)} 条")
        return reranked[:actual_top_k]

    def rerank(self, query: str, docs: List[Document], top_k: int = None,
               evidence_type: str = None) -> List[Document]:
        if not docs:
            return []

        actual_top_k = top_k if top_k is not None else self.top_k

        # 如果Rerank未启用或API密钥无效，用规则回退排序(而非原始顺序)
        if not self.enabled:
            logger.info(f"ℹ️  Rerank 功能已禁用，使用规则回退排序")
            return self._fallback_medical_rank(docs, query, evidence_type, actual_top_k)

        try:
            doc_contents = [doc.page_content for doc in docs]
            resp = dashscope.TextReRank.call(
                model=self.model,
                query=query,
                documents=doc_contents,
                top_n=actual_top_k,
                return_documents=True,
                api_key=self.api_key,
            )
            if resp.status_code == HTTPStatus.OK:
                reranked = []
                for item in resp.output.results:
                    original_doc = docs[item.index]
                    original_doc.metadata["relevance_score"] = item.relevance_score
                    reranked.append(original_doc)
                # Medical Evidence Score:语义分 + 证据类型匹配 + 指南权威 + 时效 + 人群
                reranked = self._apply_medical_score(reranked, query, evidence_type)
                self._mark_layer(reranked, "gte_api")
                logger.info(f"✅ Rerank 完成，{len(docs)} → {len(reranked)} 条")
                return reranked[:actual_top_k]
            elif resp.code == "Throttling.RateQuota":
                # 限流: 退避重试一次(并行检索打爆配额时常见)
                logger.warning(f"⚠️  Rerank 限流 ({resp.message})，1s 后重试一次")
                time.sleep(1)
                try:
                    resp = dashscope.TextReRank.call(
                        model=self.model,
                        query=query,
                        documents=doc_contents,
                        top_n=actual_top_k,
                        return_documents=True,
                        api_key=self.api_key,
                    )
                    if resp.status_code == HTTPStatus.OK:
                        reranked = []
                        for item in resp.output.results:
                            original_doc = docs[item.index]
                            original_doc.metadata["relevance_score"] = item.relevance_score
                            reranked.append(original_doc)
                        reranked = self._apply_medical_score(reranked, query, evidence_type)
                        self._mark_layer(reranked, "gte_api")
                        logger.info(f"✅ Rerank 重试成功，{len(docs)} → {len(reranked)} 条")
                        return reranked[:actual_top_k]
                except Exception as e2:
                    logger.warning(f"⚠️  Rerank 重试异常: {type(e2).__name__} - {e2}")
                logger.warning(f"⚠️  Rerank 限流重试仍失败，使用规则回退排序")
                return self._fallback_medical_rank(docs, query, evidence_type, actual_top_k)
            else:
                logger.warning(f"⚠️  Rerank API 失败 ({resp.code}): {resp.message}，使用规则回退排序")
                return self._fallback_medical_rank(docs, query, evidence_type, actual_top_k)
        except Exception as e:
            logger.warning(f"⚠️  Rerank 异常: {type(e).__name__} - {str(e)}，使用规则回退排序")
            return self._fallback_medical_rank(docs, query, evidence_type, actual_top_k)

    def _apply_medical_score(self, docs: List[Document], query: str,
                             evidence_type: str | None) -> List[Document]:
        """
        Medical Evidence Score 重排(医学化):

        Final Score = 0.20 语义相似度
                    + 0.15 证据类型匹配
                    + 0.10 指南权威
                    + 0.10 证据等级(evidence_level A/B/C)
                    + 0.10 时效性
                    + 0.10 主题(subtopic)匹配
                    + 0.10 决策节点(decision_node)匹配
                    + 0.10 干预(intervention)匹配
                    + 0.05 时间窗(time_window)匹配
                    − 0.30 不匹配 subtopic 惩罚

        依据 chunk 的 metadata(evidence_type/subtopic/decision_node/
        intervention/time_window/evidence_level/authority/year) 加权。
        决策节点/干预/时间窗匹配保证"IV alteplase 4.5h"查询优先召回
        对应决策与时限的证据, 而非仅 embedding 相似的其他指南段落。
        """
        if not docs:
            return docs

        query_lower = query.lower()
        expected_type = (evidence_type or "").strip().lower()

        # 证据类型 → 期望的 metadata evidence_type
        type_map = {
            "treatment": {"guideline", "consensus", "rct", "meta-analysis"},
            "diagnosis": {"guideline", "review", "criteria"},
            "etiology": {"guideline", "review", "criteria"},
            "anatomy": {"textbook"},
            "prognosis": {"guideline", "review"},
            "prevention": {"guideline", "consensus"},
        }
        expected_types = type_map.get(expected_type, set())

        # 干预/决策节点/时间窗 标签 → 关键词(别名匹配, 如 query "rt-pa" 命中标签 alteplase)
        from app.rag.data_loader import INTERVENTION_RULES, DECISION_NODE_RULES, TIME_WINDOW_RULES
        intervention_kws = {label: kws for label, kws in INTERVENTION_RULES}
        decision_node_kws = {label: kws for label, kws in DECISION_NODE_RULES}
        time_window_kws = {label: kws for label, kws in TIME_WINDOW_RULES}

        def _label_list(raw) -> List[str]:
            if isinstance(raw, str):
                return [s.strip() for s in raw.split(",") if s.strip()]
            if isinstance(raw, list):
                return [str(s).strip() for s in raw if str(s).strip()]
            return []

        def _labels_match(labels: List[str], kws_map: dict) -> int:
            """标签或其别名关键词命中查询的次数。"""
            matched = 0
            for label in labels:
                if label in query_lower:
                    matched += 1
                elif any(str(kw).lower() in query_lower for kw in kws_map.get(label, [])):
                    matched += 1
            return matched

        for doc in docs:
            meta = doc.metadata or {}
            score = 0.0
            reasons = []

            # 1. 语义相似度(0.20, 来自 rerank relevance_score 或 RRF 归一化)
            semantic = float(meta.get("relevance_score", 0.0) or 0.0)
            score += 0.20 * min(1.0, semantic)

            # 2. 证据类型匹配(0.15)
            ev_type = str(meta.get("evidence_type", "") or "").lower()
            if expected_types and ev_type in expected_types:
                score += 0.15
            elif not expected_types:
                score += 0.09  # 无期望类型时给基础分

            # 3. 指南权威(0.10, authority 3-5 → 0-1)
            authority = int(meta.get("authority", 3) or 3)
            score += 0.10 * min(1.0, (authority - 2) / 3.0)

            # 4. 证据等级(0.10, A/B/C/NA)
            ev_level = str(meta.get("evidence_level", "") or "").upper()
            score += {"A": 0.10, "B": 0.05, "C": 0.02}.get(ev_level, 0.02)

            # 5. 时效性(0.10, 年份越新越高)
            year = meta.get("year")
            if isinstance(year, int) and year >= 2015:
                score += 0.10 * min(1.0, (year - 2015) / 10.0)
            else:
                score += 0.03

            # 6. 主题匹配(0.10):查询关键词命中 chunk 的 subtopic
            subtopics = _label_list(meta.get("subtopic"))
            if subtopics:
                matched_kw = sum(1 for s in subtopics if str(s).lower() in query_lower)
                score += 0.10 * min(1.0, matched_kw / 2.0)

            # 7. 决策节点匹配(0.10)
            decision_nodes = _label_list(meta.get("decision_node"))
            if decision_nodes:
                score += 0.10 * min(1.0, _labels_match(decision_nodes, decision_node_kws))

            # 8. 干预匹配(0.10)
            interventions = _label_list(meta.get("intervention"))
            if interventions:
                score += 0.10 * min(1.0, _labels_match(interventions, intervention_kws))

            # 9. 时间窗匹配(0.05):查询提及时间窗且 chunk 标签一致(数字边界防误判)
            time_windows = _label_list(meta.get("time_window"))
            if time_windows:
                from app.rag.data_loader import time_window_hit
                matched_window = 0
                for label in time_windows:
                    if label in query_lower or time_window_hit(
                            query_lower, time_window_kws.get(label, [])):
                        matched_window = 1
                        break
                score += 0.05 * matched_window

            # 10. 临床意图匹配(evidence_type → 期望 clinical_intent)
            #     LLM 语义标签: 高压氧(treatment)在 etiology 查询时应减分;
            #     "general"(泛化意图)不惩罚, 避免有标签 chunk 系统性吃亏
            intent = str(meta.get("clinical_intent", "") or "").strip().lower()
            if intent and intent != "general":
                expected_intents = {
                    "treatment": {"treatment", "management", "intervention", "rehabilitation"},
                    "etiology": {"classification", "etiology", "diagnosis"},
                    "anatomy": {"localization", "anatomy"},
                    "prevention": {"prevention", "secondary_prevention"},
                    "diagnosis": {"diagnosis", "assessment", "classification"},
                }.get(expected_type, set())
                if expected_intents and intent in expected_intents:
                    score += 0.10
                elif expected_intents:
                    score -= 0.10

            # 淘汰惩罚:仅当 chunk 的所有 subtopic 均为不匹配主题时减分
            # (避免 "thrombolysis,lipid_management" 这类含相关主题的 chunk 被误杀)
            excluded = {
                "treatment": ["secondary_prevention", "lipid_management"],
                "anatomy": ["secondary_prevention", "lipid_management", "antiplatelet", "anticoagulation"],
                "etiology": ["secondary_prevention", "lipid_management"],
                "diagnosis": ["secondary_prevention", "lipid_management"],
            }.get(expected_type, [])
            if subtopics and excluded and all(s in excluded for s in subtopics):
                score -= 0.3

            doc.metadata["medical_score"] = round(score, 4)
            doc.metadata["score_reasons"] = reasons

        # 按 Medical Evidence Score 降序
        docs.sort(key=lambda d: float(d.metadata.get("medical_score", 0.0)), reverse=True)
        return docs
