"""用户直接提问提取器测试(纯逻辑, 无需真实 API)。

运行: pytest tests/test_question_extractor.py -v
"""
import sys

import pytest

sys.path.insert(0, ".")

from app.agents.utils.question_extractor import extract_user_questions


def test_extracts_plain_question():
    qs = extract_user_questions("这个患者需要抗凝治疗吗？")
    assert qs == ["这个患者需要抗凝治疗吗"]


def test_extracts_numbered_list():
    text = "请回答以下问题：1. 是否适合静脉溶栓 2. 什么时候取栓 3. 抗凝何时启动"
    qs = extract_user_questions(text)
    assert qs == ["是否适合静脉溶栓", "什么时候取栓", "抗凝何时启动"]


def test_extracts_multiple_sentences():
    text = "患者是否需要溶栓？如果溶栓，时间窗是多少？请给出建议。"
    qs = extract_user_questions(text)
    assert "患者是否需要溶栓" in qs
    assert "如果溶栓，时间窗是多少" in qs
    # 陈述句"请给出建议。"不应被提取
    assert not any("请给出建议" in q for q in qs)


def test_case_description_no_question():
    text = "患者男69岁突发右侧肢体无力2小时，NIHSS 16分，血压185/100，无出血史"
    assert extract_user_questions(text) == []


def test_supplement_statement_not_extracted():
    text = "补充信息：INR 1.1、血小板180、CTA未见大血管闭塞"
    assert extract_user_questions(text) == []


def test_question_word_start():
    qs = extract_user_questions("是否应该先做CTA评估大血管闭塞？")
    assert len(qs) == 1
    assert qs[0].startswith("是否应该先做CTA")


def test_deduplicates_and_caps():
    text = "需要抗凝吗？需要抗凝吗？需要抗凝吗？溶栓还是取栓？"
    qs = extract_user_questions(text)
    assert len(qs) == 2
    assert qs.count("需要抗凝吗") == 1


def test_empty_and_none():
    assert extract_user_questions("") == []
    assert extract_user_questions(None) == []


def test_exam_structured_questions():
    """临床综合分析题: '请写出该患者的：（1）…（2）…（3）…' 应逐问提取。"""
    exam = (
        "患者，男性，65岁。因'突发言语含糊、右侧肢体无力2小时'急诊入院。\n"
        "问题（共100分）\n"
        "1.（40分）诊断与评估\n"
        "请写出该患者的：（1）定位诊断和定性诊断（含依据）；（2）最可能的TOAST病因分型（简述理由）；"
        "（3）主要的脑卒中危险因素（至少列出4项）。"
    )
    qs = extract_user_questions(exam)
    assert qs == [
        "定位诊断和定性诊断（含依据）",
        "最可能的TOAST病因分型（简述理由）",
        "主要的脑卒中危险因素（至少列出4项）",
    ]


def test_exam_does_not_hallucinate():
    """结构化题目下不应提取出题面中不存在的问题(如'该患者是否需要溶栓?')。"""
    exam = (
        "请写出该患者的：（1）定位诊断和定性诊断（含依据）；（2）最可能的TOAST病因分型（简述理由）。"
    )
    qs = extract_user_questions(exam)
    assert all("溶栓" not in q for q in qs)
    assert len(qs) == 2


def test_exam_multiple_sections_bounded():
    """多道大题时只提取引导句后的编号项, 不串到下一道大题。"""
    text = (
        "请写出该患者的：（1）定位诊断（含依据）；（2）危险因素（至少4项）。\n"
        "2.（30分）治疗\n"
        "请说明该患者的治疗方案。"
    )
    qs = extract_user_questions(text)
    assert len(qs) == 2
    assert all("治疗方案" not in q for q in qs)


# ── 意图路由: 引用历史患者的追问强制走 consultation ──

def test_intent_force_consultation_rule():
    from app.agents.orchestrators.nodes.intent_node import IntentNode
    # 引用历史患者 + 有历史上下文 → 强制 consultation(不能误判为知识问答)
    assert IntentNode._force_consultation("该患者需要抗凝吗？", "患者男69岁房颤, 突发偏瘫2小时", "knowledge") == "consultation"
    assert IntentNode._force_consultation("这个患者什么时候可以下床？", "脑梗死急性期", "knowledge") == "consultation"
    # 无患者引用 → 保持原判
    assert IntentNode._force_consultation("脑卒中的二级预防措施有哪些？", "患者男69岁...", "knowledge") == "knowledge"
    # 无历史上下文 → 不强制(没有患者可追问)
    assert IntentNode._force_consultation("该患者需要抗凝吗？", "", "knowledge") == "knowledge"
    # 已是 consultation → 不变
    assert IntentNode._force_consultation("任意输入", "上下文", "consultation") == "consultation"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
