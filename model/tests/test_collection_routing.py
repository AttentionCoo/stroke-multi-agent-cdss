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


if __name__ == "__main__":
    unittest.main()
