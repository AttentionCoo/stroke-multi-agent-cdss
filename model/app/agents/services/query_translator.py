"""Medical Query Translator — 临床语言 → 医学数据库语言转换层。

职责：
1. 医学术语标准化：把临床描述(如"左侧大脑中动脉供血区")映射为文献标准术语
   (如 "middle cerebral artery syndrome"、"MCA infarction")
2. 同义词扩展：为检索式生成多组等价表达(提升 embedding/BM25 召回)
3. 证据源关键词注入：按证据类型附加指南/诊断标准等路由关键词

这是 Decision Planner → Retriever 之间的 Medical Evidence Router。
"""
from __future__ import annotations

import re
from typing import Dict, List

# 医学术语同义词扩展词典
# key: 标准化术语(小写);value: 等价表达列表(含中英文、缩写、全称)
SYNONYM_MAP: Dict[str, List[str]] = {
    # 血管与综合征
    "mca": ["middle cerebral artery", "mca syndrome", "mca infarction", "mca occlusion", "大脑中动脉"],
    "middle cerebral artery": ["mca", "mca syndrome", "mca infarction", "大脑中动脉"],
    "aca": ["anterior cerebral artery", "大脑前动脉"],
    "pca": ["posterior cerebral artery", "大脑后动脉"],
    "ica": ["internal carotid artery", "颈内动脉"],
    "vertebrobasilar": ["posterior circulation", "椎基底动脉"],
    # 症状体征
    "aphasia": ["失语", "language disorder", "speech disturbance", "言语障碍", "语言障碍"],
    "hemiparesis": ["hemiplegia", "偏瘫", "monoparesis", "肢体无力", "肢体瘫痪"],
    "hemianopia": ["visual field defect", "视野缺损", "偏盲"],
    "dysarthria": ["构音障碍", "言语不清", "slurred speech"],
    "neglect": ["hemineglect", "单侧忽略", "忽视"],
    "ataxia": ["共济失调", "incoordination"],
    # 卒中类型
    "ischemic stroke": ["acute ischemic stroke", "ais", "脑梗死", "缺血性卒中", "cerebral infarction"],
    "intracerebral hemorrhage": ["ich", "脑出血", "intracranial hemorrhage"],
    "tia": ["transient ischemic attack", "短暂性脑缺血发作"],
    "large vessel occlusion": ["lvo", "大血管闭塞", "proximal occlusion"],
    "cardioembolism": ["心源性栓塞", "cardioembolic stroke", "atrial fibrillation stroke"],
    "small vessel occlusion": ["lacunar stroke", "腔隙性梗死", "小动脉闭塞"],
    # 治疗
    "thrombolysis": ["alteplase", "rt-pa", "rtpa", "tissue plasminogen activator", "静脉溶栓", "阿替普酶", "tpa"],
    "thrombectomy": ["evt", "mechanical thrombectomy", "取栓", "血管内治疗", "endovascular treatment"],
    "antiplatelet": ["aspirin", "clopidogrel", "双抗", "抗血小板", "阿司匹林", "氯吡格雷"],
    "anticoagulation": ["warfarin", "novac", "doac", "抗凝", "华法林", "利伐沙班"],
    # 影像
    "cta": ["ct angiography", "ct血管造影", "血管成像"],
    "mra": ["mr angiography", "mr血管成像"],
    "ctp": ["ct perfusion", "ct灌注"],
    "dwi": ["diffusion weighted imaging", "弥散加权成像"],
    "mri": ["magnetic resonance imaging", "磁共振"],
    # 评估
    "nihss": ["national institutes of health stroke scale", "美国国立卫生研究院卒中量表", "卒中量表"],
    "gcs": ["glasgow coma scale", "格拉斯哥昏迷量表", "格拉斯哥评分"],
    "mrs": ["modified rankin scale", "改良rankin量表"],
    "toast": ["toast classification", "toast分型", "stroke subtype classification", "卒中分型"],
    "aspects": ["alberta stroke program early ct score"],
    # 病因/风险
    "hypertension": ["高血压", "elevated blood pressure", "bp", "血压升高"],
    "atrial fibrillation": ["af", "房颤", "atrial flutter"],
    "hyperlipidemia": ["高脂血症", "dyslipidemia", "血脂异常"],
    "diabetes": ["糖尿病", "diabetes mellitus", "dm"],
    # 证据类型路由关键词
    "guideline": ["指南", "guideline", "共识", "management", "treatment recommendation"],
    "diagnostic_criteria": ["diagnostic criteria", "classification", "诊断标准", "分型标准"],
    "textbook": ["textbook", "神经解剖", "neuroanatomy", "教材"],
}

# 证据类型 → 应注入的路由关键词
EVIDENCE_TYPE_KEYWORDS = {
    "treatment": ["guideline", "thrombolysis", "thrombectomy", "推荐", "适应证", "禁忌证"],
    "diagnosis": ["diagnostic criteria", "diagnosis", "诊断标准", "鉴别"],
    "etiology": ["toast", "classification", "病因", "分型"],
    "anatomy": ["mca", "localization", "神经解剖", "syndrome", "定位"],
    "prognosis": ["prognosis", "outcome", "复发", "预后"],
    "prevention": ["secondary prevention", "二级预防", "antiplatelet", "抗血小板"],
}


def _tokenize(text: str) -> List[str]:
    """拆分中英文 token。"""
    # 中文按字连续块,英文按词
    parts = re.findall(r"[\u4e00-\u9fff]+|[A-Za-z][A-Za-z\-]*", text.lower())
    return parts


def expand_synonyms(text: str, max_variants: int = 4) -> List[str]:
    """
    同义词扩展:识别文本中的医学术语,生成多组等价查询。

    返回扩展后的查询变体列表(含原查询)。
    """
    lower = text.lower()
    variants: List[str] = [text]
    seen = {text.strip().casefold()}

    matched_terms = []
    for term, synonyms in SYNONYM_MAP.items():
        if term in lower or any(syn in lower for syn in synonyms):
            matched_terms.append((term, synonyms))

    # 为每个匹配术语生成"原词替换为同义词"的变体
    for term, synonyms in matched_terms[:5]:
        for syn in synonyms[:3]:
            # 替换文本中的术语(精确词边界)
            new_text = _replace_term(text, term, syn)
            key = new_text.strip().casefold()
            if key and key not in seen:
                seen.add(key)
                variants.append(new_text)
            if len(variants) >= max_variants + 1:
                break
        if len(variants) >= max_variants + 1:
            break

    return variants[: max_variants + 1]


def _replace_term(text: str, term: str, replacement: str) -> str:
    """替换文本中的术语(保留大小写无关)。"""
    pattern = re.compile(re.escape(term), re.IGNORECASE)
    return pattern.sub(replacement, text)


def inject_evidence_keywords(query: str, evidence_type: str | None) -> str:
    """
    按证据类型注入路由关键词。

    例如 treatment 查询会附加 "guideline/推荐/适应证" 等词,
    提高向量检索召回指南类文档的概率。
    """
    if not evidence_type:
        return query
    keywords = EVIDENCE_TYPE_KEYWORDS.get(evidence_type.strip().lower())
    if not keywords:
        return query
    # 只注入查询中未出现的路由关键词(避免膨胀)
    to_add = [kw for kw in keywords if kw.lower() not in query.lower()]
    if not to_add:
        return query
    return f"{query} {' '.join(to_add[:3])}"


def translate_query(query: str, evidence_type: str | None = None) -> List[str]:
    """
    完整转换:术语标准化 + 同义词扩展 + 证据源关键词注入。

    Args:
        query: 临床检索式
        evidence_type: 决策类型(treatment/diagnosis/etiology/anatomy/...)

    Returns:
        一组待检索的查询变体(用于多路召回)
    """
    # 1. 证据类型关键词注入
    enriched = inject_evidence_keywords(query, evidence_type)
    # 2. 同义词扩展
    variants = expand_synonyms(enriched)
    # 3. 若无任何扩展,保留原查询
    if not variants:
        variants = [query]
    return variants
