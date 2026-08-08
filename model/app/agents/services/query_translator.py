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
    "ischemic stroke": ["acute ischemic stroke", "ais", "脑梗死", "缺血性卒中", "脑卒中", "cerebral infarction", "卒中"],
    "intracerebral hemorrhage": ["ich", "脑出血", "intracranial hemorrhage"],
    "tia": ["transient ischemic attack", "短暂性脑缺血发作"],
    "large vessel occlusion": ["lvo", "大血管闭塞", "proximal occlusion"],
    "cardioembolism": ["心源性栓塞", "cardioembolic stroke", "atrial fibrillation stroke"],
    "small vessel occlusion": ["lacunar stroke", "腔隙性梗死", "小动脉闭塞"],
    # 治疗
    "thrombolysis": ["alteplase", "rt-pa", "rtpa", "tissue plasminogen activator", "静脉溶栓", "溶栓", "阿替普酶", "tpa"],
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


def extract_medical_concepts(query: str) -> Dict[str, List[str]]:
    """
    Medical Concept Normalizer:从临床查询中抽取医学概念及其同义词组。

    返回 {"概念名": [该概念的标准术语+同义词]}。
    概念顺序按在查询中出现的先后排列。
    """
    lower = query.lower()
    concepts: Dict[str, List[str]] = {}

    for term, synonyms in SYNONYM_MAP.items():
        # 匹配:查询中包含该术语或其任一同义词
        matched = term in lower or any(syn.lower() in lower for syn in synonyms)
        if not matched:
            continue
        # 概念组 = 标准术语 + 同义词(去重,最多 4 个)
        group = [term] + synonyms
        unique_group = []
        seen = set()
        for g in group:
            key = g.casefold()
            if key not in seen:
                seen.add(key)
                unique_group.append(g)
        concepts[term] = unique_group[:4]

    return concepts


def build_or_and_query(concepts: Dict[str, List[str]], max_concepts: int = 4) -> str:
    """
    将抽取的概念组合为 OR-AND 检索式:
    ("概念A同义词1" OR "概念A同义词2") AND ("概念B同义词1" OR ...) AND ...
    """
    if not concepts:
        return ""
    terms = list(concepts.items())[:max_concepts]
    clauses = []
    used_synonyms: set = set()
    for _term, synonyms in terms:
        # 过滤掉已在其他概念组用过的同义词(避免交叉重复)
        fresh = []
        for s in synonyms:
            key = s.casefold()
            if key not in used_synonyms:
                used_synonyms.add(key)
                fresh.append(s)
        if not fresh:
            continue
        if len(fresh) == 1:
            clauses.append(f'"{fresh[0]}"')
        else:
            quoted = [f'"{s}"' for s in fresh[:3]]
            clauses.append("(" + " OR ".join(quoted) + ")")
    return " AND ".join(clauses)


# 证据类型 → 来源约束词(附加到检索式, 约束证据源)
SOURCE_CONSTRAINTS = {
    "treatment": ["guideline", "recommendation", "meta-analysis", "RCT", "指南", "治疗推荐"],
    "diagnosis": ["diagnostic criteria", "classification", "诊断标准", "鉴别诊断"],
    "etiology": ["TOAST", "classification", "病因", "分型", "diagnostic criteria"],
    "anatomy": ["neurology textbook", "neuroanatomy", "clinical localization", "syndrome", "神经解剖", "定位"],
    "prognosis": ["prognosis", "outcome", "预后", "mortality"],
    "prevention": ["secondary prevention", "二级预防", "guideline", "指南"],
}


def add_source_constraint(query: str, evidence_type: str | None) -> str:
    """
    Source Constraint:按证据类型附加来源约束词。

    例: anatomy 查询 → "... AND (neurology textbook OR clinical localization)"
    避免检索撞上 stroke prevention(二级预防)等无关内容。
    """
    if not evidence_type:
        return query
    keywords = SOURCE_CONSTRAINTS.get(evidence_type.strip().lower())
    if not keywords:
        return query
    # 只追加查询中未出现的约束词(取前 2 个)
    to_add = [kw for kw in keywords if kw.lower() not in query.lower()]
    if not to_add:
        return query
    constraint = " OR ".join(f'"{kw}"' for kw in to_add[:2])
    return f"{query} AND ({constraint})"


def abstract_patient_variables(query: str) -> str:
    """
    Query Abstraction:移除患者特定变量(年龄/NIHSS/ASPECTS/血压等具体数值),
    保留医学概念,使检索匹配文献而非病例。

    例: "NIHSS18 ASPECTS10 房颤卒中" → "atrial fibrillation acute ischemic stroke"
    """
    # 移除具体数值与量表分数模式
    patterns = [
        r"nihss\s*[:：=]?\s*\d{1,2}\s*分?",      # NIHSS 18分
        r"aspects\s*[:：=]?\s*\d{1,2}\s*分?",     # ASPECTS 10分
        r"gcs\s*[:：=]?\s*\d{1,2}\s*分?",         # GCS 15分
        r"\b\d{1,3}\s*岁\b",                     # 69岁
        r"血压\s*[:：=]?\s*\d{2,3}\s*[/／]\s*\d{2,3}",  # 血压 185/110
        r"(?:收缩压|高压)\s*[:：=]?\s*\d{2,3}",
        r"血小板\s*[:：=]?\s*\d+",
        r"发病\s*\d+(\.\d+)?\s*(小时|分钟)",
        r"\b\d+(\.\d+)?\s*(小时|h|hrs?)\b",
    ]
    abstracted = query
    for p in patterns:
        abstracted = re.sub(p, "", abstracted, flags=re.IGNORECASE)
    # 清理多余空格与连接词
    abstracted = re.sub(r"\s+", " ", abstracted).strip()
    abstracted = re.sub(r"\s+(AND|OR)\s+$", "", abstracted, flags=re.IGNORECASE)
    # 清理残留的孤立"分"字(如 "NIHSS18分" 移除后残留)
    abstracted = re.sub(r"(?<!\d)\s*分\s*(?!\d)", " ", abstracted)
    abstracted = re.sub(r"\s+", " ", abstracted).strip()
    return abstracted


# ---- PICO 结构化查询 ----
# SYNONYM_MAP 中属于"干预(I)"的概念(其余视为"人群/疾病(P)")
PICO_INTERVENTION_TERMS = {"thrombolysis", "thrombectomy", "antiplatelet", "anticoagulation"}

# clinical_question:查询语气 → 证据问题类型
CLINICAL_QUESTION_RULES = [
    ("eligibility", ["是否", "可不可以", "能否", "能不能", "适用", "eligible", "indication", "适应证", "适应症"]),
    ("contraindication", ["禁忌", "不能", "不可", "contraindication", "禁忌证", "禁忌症"]),
]


def extract_time_window(query: str) -> str | None:
    """从查询中提取时间窗标签(如 0-4.5h), 无则 None。"""
    from app.rag.data_loader import TIME_WINDOW_RULES, time_window_hit
    lower = query.lower()
    for label, kws in TIME_WINDOW_RULES:
        if time_window_hit(lower, kws):
            return label
    return None


def build_pico_query(query: str, evidence_type: str | None = None) -> str:
    """
    PICO 结构化查询生成:
        (P 人群/疾病) AND (I 干预) AND (时间窗) AND (clinical_question)

    例: "NIHSS18 房颤卒中 3小时 是否溶栓"
      → ("acute ischemic stroke" OR "atrial fibrillation" OR ...)
        AND ("thrombolysis" OR "alteplase" OR "静脉溶栓" OR ...)
        AND ("3小时" OR "3h") AND ("eligibility")

    相比纯概念 OR-AND 组合, PICO 明确区分人群/干预/时限/临床问题,
    使检索式更贴近"临床决策 → 证据空间"的映射。
    """
    concepts = extract_medical_concepts(query)
    if not concepts:
        return ""

    p_terms, i_terms = [], []
    used: set = set()
    for term, synonyms in concepts.items():
        core = [term] + list(synonyms)[:3]
        target = i_terms if term in PICO_INTERVENTION_TERMS else p_terms
        for c in core:
            key = str(c).casefold()
            if key not in used:
                used.add(key)
                target.append(f'"{c}"')

    if not p_terms:
        return ""

    clauses = ["(" + " OR ".join(p_terms) + ")"]
    if i_terms:
        clauses.append("(" + " OR ".join(i_terms) + ")")

    # 时间窗(如 "3小时" OR "3h")
    tw = extract_time_window(query)
    if tw:
        from app.rag.data_loader import TIME_WINDOW_RULES
        kws = dict(TIME_WINDOW_RULES).get(tw, [])
        if kws:
            clauses.append("(" + " OR ".join(f'"{k}"' for k in kws[:2]) + ")")

    # clinical_question(eligibility/contraindication)
    lower = query.lower()
    cqs = [label for label, kws in CLINICAL_QUESTION_RULES
           if any(str(kw).lower() in lower for kw in kws)]
    if cqs:
        clauses.append("(" + " OR ".join(f'"{c}"' for c in cqs) + ")")

    pico = " AND ".join(clauses)
    # 证据类型关键词注入
    if evidence_type:
        pico = inject_evidence_keywords(pico, evidence_type)
    return pico


def translate_query(query: str, evidence_type: str | None = None) -> List[str]:
    """
    完整转换:Medical Concept Normalizer(概念抽取+OR组合) + 同义词扩展 + 证据源关键词。

    Args:
        query: 临床检索式
        evidence_type: 决策类型(treatment/diagnosis/etiology/anatomy/...)

    Returns:
        一组待检索的查询变体:
        1. OR-AND 组合式(医学检索范式)
        2. 原始查询 + 证据关键词
        3. 同义词替换变体
    """
    # 1. 医学概念抽取 + OR-AND 组合(医学检索范式)
    concepts = extract_medical_concepts(query)
    or_and = build_or_and_query(concepts) if concepts else ""

    # 2. Query Abstraction:患者变量 → 医学概念(去除 NIHSS/ASPECTS/年龄等)
    abstracted = abstract_patient_variables(query)

    # 3. 证据类型关键词注入
    enriched = inject_evidence_keywords(query, evidence_type)
    abstracted_enriched = inject_evidence_keywords(abstracted, evidence_type)

    # 3.5 Source Constraint:按证据类型附加来源约束词(如 anatomy → textbook/定位)
    if or_and:
        or_and = add_source_constraint(or_and, evidence_type)
    if abstracted_enriched:
        abstracted_enriched = add_source_constraint(abstracted_enriched, evidence_type)

    # 4. 同义词替换变体
    variants = []
    # 4.5 PICO 结构化查询(最贴近临床决策 → 证据映射, 优先检索)
    pico = build_pico_query(query, evidence_type)
    if pico:
        variants.append(pico)
    if abstracted_enriched and abstracted_enriched.strip().casefold() != enriched.strip().casefold():
        variants.append(abstracted_enriched)  # 抽象后查询优先
    if or_and:
        variants.append(or_and)
    if enriched not in variants:
        variants.append(enriched)

    for v in expand_synonyms(enriched):
        if v not in variants:
            variants.append(v)

    # 去重保序
    seen = set()
    result = []
    for v in variants:
        key = v.strip().casefold()
        if key and key not in seen:
            seen.add(key)
            result.append(v)
    return result
