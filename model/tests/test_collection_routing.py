"""Multi-Collection 归属规则单元测试(纯逻辑, 不依赖外部 API)。

验证:
- route_collection 按 教材/治疗/预防/病因/默认 正确归属 chunk
- 缺失 subtopic 的文档(如 QA 对)可从内容关键词提取归属
- bucket_chunks_by_collection 汇总正确
- retrieval_service 的 evidence_type → collections 路由映射
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain_core.documents import Document

from app.rag.retrievers import (
    COLLECTION_NAMES,
    route_collection,
    bucket_chunks_by_collection,
)
from app.agents.services.retrieval_service import route_collections


def make_doc(content: str, category: str = "指南", subtopic: str = "") -> Document:
    meta = {"source": "test.pdf", "category": category}
    if subtopic:
        meta["subtopic"] = subtopic
    return Document(page_content=content, metadata=meta)


class TestRouteCollection(unittest.TestCase):

    def test_textbook_to_anatomy(self):
        doc = make_doc("大脑中动脉供血区解剖", category="教材", subtopic="imaging")
        self.assertEqual(route_collection(doc.metadata, doc.page_content), "anatomy")

    def test_treatment_subtopic(self):
        doc = make_doc("rt-PA 静脉溶栓时间窗", category="指南", subtopic="thrombolysis")
        self.assertEqual(route_collection(doc.metadata, doc.page_content), "treatment")

    def test_treatment_from_content_when_subtopic_missing(self):
        # 旧库 QA 对等无 subtopic 字段 → 从内容关键词提取
        doc = make_doc("阿替普酶静脉溶栓的适应证与禁忌证", category="指南", subtopic="")
        self.assertEqual(route_collection(doc.metadata, doc.page_content), "treatment")

    def test_prevention_subtopic(self):
        doc = make_doc("二级预防抗凝治疗", category="指南", subtopic="anticoagulation")
        self.assertEqual(route_collection(doc.metadata, doc.page_content), "prevention")

    def test_lipid_guideline_not_anatomy(self):
        # 核心场景: 血脂指南内容绝不能进入 anatomy
        doc = make_doc("他汀类药物降 LDL 治疗", category="指南", subtopic="lipid_management")
        self.assertEqual(route_collection(doc.metadata, doc.page_content), "prevention")
        self.assertNotEqual(route_collection(doc.metadata, doc.page_content), "anatomy")

    def test_etiology_subtopic(self):
        doc = make_doc("TOAST 病因分型", category="指南", subtopic="toast_classification")
        self.assertEqual(route_collection(doc.metadata, doc.page_content), "etiology")

    def test_default_guideline(self):
        # 无主题/宽泛主题(如仅 stroke_identification) → guideline
        doc = make_doc("本指南的适用范围与编写说明", category="指南", subtopic="stroke_identification")
        self.assertEqual(route_collection(doc.metadata, doc.page_content), "guideline")

    def test_treatment_priority_over_prevention(self):
        # 同时命中治疗+预防主题 → 按优先级归 treatment
        doc = make_doc("溶栓后何时启动抗凝", category="指南", subtopic="thrombolysis,anticoagulation")
        self.assertEqual(route_collection(doc.metadata, doc.page_content), "treatment")

    def test_bucket_chunks(self):
        chunks = [
            make_doc("神经解剖", category="教材"),
            make_doc("静脉溶栓", category="指南", subtopic="thrombolysis"),
            make_doc("抗凝预防", category="指南", subtopic="anticoagulation"),
            make_doc("TOAST 分型", category="指南", subtopic="toast_classification"),
            make_doc("指南总论", category="指南"),
        ]
        buckets = bucket_chunks_by_collection(chunks)
        self.assertEqual(len(buckets["anatomy"]), 1)
        self.assertEqual(len(buckets["treatment"]), 1)
        self.assertEqual(len(buckets["prevention"]), 1)
        self.assertEqual(len(buckets["etiology"]), 1)
        self.assertEqual(len(buckets["guideline"]), 1)
        self.assertEqual(sum(len(v) for v in buckets.values()), len(chunks))

    def test_collection_names_suffix(self):
        for key, name in COLLECTION_NAMES.items():
            self.assertTrue(name.endswith("_collection"))
            self.assertTrue(name.startswith(key))


class TestEvidenceTypeRouting(unittest.TestCase):

    def test_mapping(self):
        self.assertEqual(route_collections("treatment"), ["treatment"])
        self.assertEqual(route_collections("anatomy"), ["anatomy"])
        self.assertEqual(route_collections("etiology"), ["etiology"])
        self.assertEqual(route_collections("prevention"), ["prevention"])
        self.assertEqual(route_collections("diagnosis"), ["guideline", "etiology"])
        self.assertEqual(route_collections("prognosis"), ["guideline", "prevention"])
        self.assertIsNone(route_collections(None))
        self.assertIsNone(route_collections("unknown_type"))

    def test_anatomy_excludes_lipid(self):
        # anatomy 路由只查 anatomy collection, 血脂指南在 prevention, 物理隔离
        self.assertNotIn("prevention", route_collections("anatomy"))


class TestMedicalEvidenceScore(unittest.TestCase):
    """Medical Evidence Score 规则评分测试(不依赖 rerank API)。"""

    @classmethod
    def setUpClass(cls):
        from app.rag.retrievers import BGEReranker
        cls.reranker = BGEReranker(top_k=3)

    def _doc(self, content, meta):
        return Document(page_content=content, metadata=meta)

    def test_fallback_rank_puts_intervention_match_first(self):
        """无 rerank API 时, 规则回退应把干预匹配的 chunk 排第一(而非 embedding 顺序)。"""
        docs = [
            self._doc("MCA 供血区解剖", {"evidence_type": "textbook", "subtopic": "imaging",
                                       "intervention": "", "decision_node": "",
                                       "evidence_level": "NA", "time_window": "",
                                       "authority": 3, "year": 2018, "rrf_score": 0.030}),
            self._doc("二级预防抗凝治疗", {"evidence_type": "guideline", "subtopic": "anticoagulation,secondary_prevention",
                                       "intervention": "warfarin", "decision_node": "anticoagulation",
                                       "evidence_level": "A", "time_window": "",
                                       "authority": 5, "year": 2022, "rrf_score": 0.028}),
            self._doc("rt-PA 静脉溶栓 4.5 小时时间窗", {"evidence_type": "guideline", "subtopic": "thrombolysis",
                                                    "intervention": "alteplase", "decision_node": "iv_thrombolysis",
                                                    "evidence_level": "A", "time_window": "0-4.5h",
                                                    "authority": 5, "year": 2023, "rrf_score": 0.032}),
        ]
        result = self.reranker._fallback_medical_rank(
            docs, "IV alteplase 急性缺血性卒中静脉溶栓 4.5小时", "treatment", 3)
        self.assertEqual(result[0].metadata["intervention"], "alteplase")
        self.assertTrue(result[0].metadata["medical_score"] > 0.5)

    def test_intervention_boost_scores(self):
        """干预匹配 + 权威 + 时效 → 高医学分。"""
        doc = self._doc("rt-PA 静脉溶栓", {"evidence_type": "guideline", "subtopic": "thrombolysis",
                                          "intervention": "alteplase", "decision_node": "iv_thrombolysis",
                                          "evidence_level": "A", "time_window": "0-4.5h",
                                          "authority": 5, "year": 2023})
        out = self.reranker._apply_medical_score([doc], "alteplase 溶栓", "treatment")
        self.assertGreater(out[0].metadata["medical_score"], 0.5)

    def test_prevention_penalty_for_treatment(self):
        """treatment 查询中纯 prevention subtopic 被惩罚(-0.3)。"""
        doc = self._doc("二级预防血脂管理", {"evidence_type": "guideline",
                                            "subtopic": "secondary_prevention,lipid_management",
                                            "intervention": "statin", "decision_node": "lipid_management",
                                            "evidence_level": "A", "time_window": "",
                                            "authority": 5, "year": 2022})
        out = self.reranker._apply_medical_score([doc], "alteplase 溶栓", "treatment")
        self.assertLess(out[0].metadata["medical_score"], 0.3)

    def test_mixed_subtopic_not_penalized(self):
        """含相关主题的混合 subtopic(如 thrombolysis,lipid_management)不惩罚。"""
        doc = self._doc("溶栓章节含血脂讨论", {"evidence_type": "guideline",
                                            "subtopic": "thrombolysis,lipid_management",
                                            "intervention": "alteplase", "decision_node": "iv_thrombolysis",
                                            "evidence_level": "A", "time_window": "0-4.5h",
                                            "authority": 5, "year": 2023})
        out = self.reranker._apply_medical_score([doc], "alteplase 溶栓", "treatment")
        self.assertGreater(out[0].metadata["medical_score"], 0.5)

    def test_intervention_alias_match(self):
        """query 用别名(rt-pa)也应命中 intervention=alteplase 的 chunk。"""
        doc = self._doc("阿替普酶静脉溶栓", {"evidence_type": "guideline", "subtopic": "thrombolysis",
                                          "intervention": "alteplase", "decision_node": "iv_thrombolysis",
                                          "evidence_level": "A", "time_window": "0-4.5h",
                                          "authority": 5, "year": 2023})
        out = self.reranker._apply_medical_score([doc], "rt-pa 溶栓", "treatment")
        self.assertGreater(out[0].metadata["medical_score"], 0.5)


class TestInterventionExtraction(unittest.TestCase):
    """intervention 元数据提取(与 enrich_metadata 同规则)。"""

    def test_extract_alteplase(self):
        from app.rag.data_loader import enrich_metadata
        meta = enrich_metadata("中国急性缺血性卒中诊治指南2023.pdf",
                               "rt-PA 静脉溶栓的适应证, 阿替普酶 0.9mg/kg", "指南")
        self.assertIn("alteplase", meta["intervention"])

    def test_extract_thrombectomy(self):
        from app.rag.data_loader import enrich_metadata
        meta = enrich_metadata("急性缺血性脑卒中血管内治疗中国专家共识.pdf",
                               "机械取栓 支架取栓 血管内治疗", "专家共识")
        self.assertIn("mechanical_thrombectomy", meta["intervention"])

    def test_no_intervention(self):
        from app.rag.data_loader import enrich_metadata
        meta = enrich_metadata("指南总论.pdf", "本指南适用范围与编写说明", "指南")
        self.assertEqual(meta["intervention"], "")


class TestStructuredMetadata(unittest.TestCase):
    """decision_node / evidence_level / time_window 元数据提取。"""

    def test_decision_node_thrombolysis(self):
        from app.rag.data_loader import enrich_metadata
        meta = enrich_metadata("中国急性缺血性卒中诊治指南2023.pdf",
                               "阿替普酶静脉溶栓治疗", "指南")
        self.assertIn("iv_thrombolysis", meta["decision_node"])

    def test_decision_node_thrombectomy(self):
        from app.rag.data_loader import enrich_metadata
        meta = enrich_metadata("血管内治疗专家共识.pdf", "机械取栓 血管内治疗", "专家共识")
        self.assertIn("mechanical_thrombectomy", meta["decision_node"])

    def test_evidence_level(self):
        from app.rag.data_loader import enrich_metadata
        meta = enrich_metadata("诊治指南.pdf", "Ⅰ级推荐 A级证据 静脉溶栓", "指南")
        self.assertEqual(meta["evidence_level"], "A")

    def test_evidence_level_grade_takes_precedence(self):
        # "Ⅰ级推荐,B级证据" 并存时以证据等级 B 为准, 不被推荐等级干扰
        from app.rag.data_loader import enrich_metadata
        meta = enrich_metadata("诊治指南.pdf", "Ⅰ级推荐 B级证据 静脉溶栓", "指南")
        self.assertEqual(meta["evidence_level"], "B")

    def test_time_window(self):
        from app.rag.data_loader import enrich_metadata
        meta = enrich_metadata("诊治指南.pdf", "4.5小时内静脉溶栓", "指南")
        self.assertIn("0-4.5h", meta["time_window"])

    def test_time_window_no_substring_false_positive(self):
        # "13小时" 不应误中 "3小时"; "14.5h" 不应误中 "4.5h"
        from app.rag.data_loader import enrich_metadata, time_window_hit
        meta = enrich_metadata("诊治指南.pdf", "发病13小时 影像学评估", "指南")
        self.assertNotIn("0-3h", meta["time_window"])
        self.assertFalse(time_window_hit("14.5h", ["4.5h"]))
        self.assertTrue(time_window_hit("4.5h", ["4.5h"]))


class TestPicoQuery(unittest.TestCase):
    """PICO 结构化查询生成。"""

    def test_build_pico(self):
        from app.agents.services.query_translator import build_pico_query
        q = build_pico_query("NIHSS18 房颤卒中 3小时 是否溶栓", "treatment")
        # P 组(人群/疾病) + I 组(干预) + 时间窗 + clinical_question
        self.assertIn("thrombolysis", q)
        self.assertIn("alteplase", q)
        self.assertIn("3小时", q)
        self.assertIn("eligibility", q)
        self.assertTrue(q.count(" AND ") >= 3)

    def test_build_pico_contraindication(self):
        from app.agents.services.query_translator import build_pico_query
        q = build_pico_query("急性缺血性卒中 溶栓禁忌证", "treatment")
        self.assertIn("contraindication", q)

    def test_translate_query_includes_pico_first(self):
        from app.agents.services.query_translator import translate_query
        variants = translate_query("急性缺血性卒中 静脉溶栓", "treatment")
        self.assertTrue(variants)
        self.assertIn("thrombolysis", variants[0])


if __name__ == "__main__":
    unittest.main()
