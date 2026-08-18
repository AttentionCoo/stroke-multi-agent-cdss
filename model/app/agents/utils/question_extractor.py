"""用户直接提问提取器。

用途: 把用户输入中的直接问句提取为 user_questions,
使 reason/debate/report 节点切换到"按用户问题逐项回答"契约,
而不是把每个追问都当成一次全新完整会诊。

覆盖两类输入:
1. 显式编号列表("请回答以下问题：1. 是否溶栓 2. 何时取栓");
2. 自然语言问句(以 ?/？/吗/呢 结尾, 或以 是否/如何/为什么 等开头)。

不误伤: 纯病例描述或"补充信息：..."这类陈述不提取。
"""

import re
from typing import List

_MAX_QUESTIONS = 6

_QUESTION_ENDINGS = ("？", "?", "吗", "呢")
_QUESTION_STARTS = (
    "是否", "如何", "怎么", "为什么", "为何", "能不能", "可不可以", "可否",
    "要不要", "需不需要", "是否需要", "是不是", "何时", "多少", "哪些",
    "哪个", "什么", "哪",
)
# 显式提问引导词
_LIST_HINTS = ("请回答以下问题", "回答下列问题", "请回答下面", "依次回答", "请分别回答")

# "请写出该患者的：（1）xxx；（2）yyy；..." 式结构化题目(临床综合分析题/考题)
_INSTRUCTION_VERB = r"(?:请写出|请回答|请说明|请列出|请给出|请分析|请评估|回答|写出|简述)"
_PATIENT_INSTRUCTION = re.compile(
    _INSTRUCTION_VERB + r".{0,12}?(?:该患者|该病人|此患者|该病例|以下问题|如下问题).{0,8}?[:：]"
)
# 下一个大题标题(如 "2.（30分）" / "问题3"), 用于截断题目区间
_NEXT_SECTION = re.compile(r"\n?\s*\d+[.、]?[（(]\d+\s*分[)）]|\n?\s*问题\s*\d+")

# 编号前缀(1. / 1、 / 1． / 1) / 1）)
# 严格版: 前缀前须为行首/：:。;；/空格, 且前缀后须有空格
# (避免把化验值 "INR 1.1"、"血小板180、" 误判为编号列表)
_STRICT_PREFIX = re.compile(r"(?:^|[\n：:。;； ])\s*\d+[.、．)）]\s")
# 宽松版: 仅在有显式列表引导词("请回答以下问题：")时使用
_LENIENT_PREFIX = re.compile(r"\d+[.、．)）]")
# 句子: 内容 + 可选句末标点(保留 ?/？ 以便判问句)
_SENTENCE = re.compile(r"[^。！？\n;；!?]+[。！？\n;；!?]?")


def split_sentences(text: str) -> List[str]:
    """按中英文句末标点/换行拆句(保留句末标点)。"""
    return [s.strip() for s in _SENTENCE.findall(text or "") if s.strip()]


def _clean(q: str) -> str:
    """去编号前缀与句末问号, 保持问题原文简洁。"""
    q = re.sub(r"^\s*(?:\d+[.、．)）]|[（(]\d+[)）])\s*", "", q).strip()
    return q.rstrip("？?").strip()


def _extract_numbered(text: str, matches) -> List[str]:
    """按编号前缀位置依次截取每个编号项内容(到下一编号或结尾)。"""
    if len(matches) < 2:
        return []
    out: List[str] = []
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        seg = _clean(text[start:end].split("。")[0])
        if len(seg) >= 2 and seg not in out:
            out.append(seg)
    return out


def _extract_patient_instruction_questions(text: str) -> List[str]:
    """处理'请写出该患者的：（1）定位诊断和定性诊断（含依据）；（2）…；（3）…' 式结构化题目。

    这类题目的小问以 （N）/ N. / N、 编号、以 分号/句号 结尾, 不含问号,
    是临床综合分析题/考题的常见形态, 必须提取为逐问回答。
    """
    m = _PATIENT_INSTRUCTION.search(text or "")
    if not m:
        return []
    rest = text[m.end():]
    # 截断到下一个大题标题("2.（30分）"/"问题3"), 避免串到其他大题
    rest = _NEXT_SECTION.split(rest)[0]
    # 按 （N）/ N. / N、 编号切分
    parts = re.split(r"[（(]\d+[)）]|\d+[.、．)）]", rest)
    out: List[str] = []
    for p in parts:
        q = re.sub(r"[。；;，,\s]+$", "", p).strip()
        if len(q) >= 2 and q not in out:
            out.append(q)
    return out


def extract_user_questions(text) -> List[str]:
    """提取用户直接提出的问题(原文), 无提问返回空列表。"""
    if not text:
        return []

    # 0) 结构化题目(请写出该患者的：（1）…（2）…) 优先
    structured = _extract_patient_instruction_questions(text)
    if structured:
        return structured[:_MAX_QUESTIONS]

    # 1) 显式编号列表优先: 有引导词时用宽松编号, 否则严格编号需 ≥2 项
    has_hint = any(h in text for h in _LIST_HINTS)
    if has_hint:
        numbered = _extract_numbered(text, list(_LENIENT_PREFIX.finditer(text)))
        if numbered:
            return numbered[:_MAX_QUESTIONS]
    strict_matches = list(_STRICT_PREFIX.finditer(text))
    if len(strict_matches) >= 2:
        numbered = _extract_numbered(text, strict_matches)
        if numbered:
            return numbered[:_MAX_QUESTIONS]

    # 2) 自然语言问句: 逐句判断
    questions: List[str] = []
    for sent in split_sentences(text):
        q = _clean(sent)
        if len(q) < 2 or len(q) > 120:
            continue
        if sent.endswith(_QUESTION_ENDINGS) or q.startswith(_QUESTION_STARTS):
            if q not in questions:
                questions.append(q)
        if len(questions) >= _MAX_QUESTIONS:
            break

    return questions
