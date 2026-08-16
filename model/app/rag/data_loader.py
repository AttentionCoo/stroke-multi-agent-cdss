import os
import json
import logging
import re
from typing import Dict, List
import numpy as np
from pypdf import PdfReader
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

logger = logging.getLogger(__name__)

# 文档分类映射:按文件名关键词归入类别
CATEGORY_RULES = [
    # (类别, 关键词列表)
    ("指南", ["诊治指南", "防治指南", "管理指南", "治疗指南", "诊疗指南", "指南2023", "指南2022", "指南2024", "指南（2023", "指南（2024", "防治指南", "guidelines", "ais", "acute ischemic stroke"]),
    ("专家共识", ["专家共识", "急诊急救", "流程与规范"]),
    ("规范", ["指导规范", "防治规范"]),
    ("教材", ["Neuroanatomy", "Blumenfeld", "Clinical Cases"]),
]

# 默认分类(未命中任何规则时)
DEFAULT_CATEGORY = "其他"

# Evidence Metadata 增强规则

# 主题(subtopic)关键词 → 结构化标签
SUBTOPIC_RULES = [
    # (标签, 关键词列表)
    ("thrombolysis", ["溶栓", "阿替普酶", "rt-pa", "rtpa", "alteplase", "静脉溶栓", "tpa", "组织型纤溶酶原激活剂"]),
    ("thrombectomy", ["取栓", "血管内治疗", "thrombectomy", "机械取栓", "evt", "支架取栓", "抽吸取栓"]),
    ("blood_pressure", ["血压管理", "降压", "收缩压", "舒张压", "血压控制", "blood pressure"]),
    ("antiplatelet", ["抗血小板", "阿司匹林", "氯吡格雷", "双抗", "antiplatelet", "aspirin", "clopidogrel"]),
    ("anticoagulation", ["抗凝", "华法林", "利伐沙班", "达比加群", "肝素", "anticoagul", "warfarin", "novac", "doac"]),
    ("lipid_management", ["血脂", "他汀", "ldl", "降脂", "statins", "lipid", "低密度脂蛋白", "阿托伐他汀", "瑞舒伐他汀"]),
    ("secondary_prevention", ["二级预防", "卒中复发", "复发风险", "secondary prevention", "复发预防"]),
    ("toast_classification", ["toast", "分型", "病因分型", "卒中分型", "classification", "大动脉粥样硬化", "心源性栓塞", "小动脉闭塞"]),
    ("lvo_assessment", ["大血管闭塞", "lvo", "cta", "ct血管造影", "mra", "闭塞评估", "血管成像", "large vessel"]),
    ("imaging", ["ct", "mri", "dwi", "aspects", "影像学", "头颅ct", "核磁", "灌注", "ctp"]),
    ("nihss_assessment", ["nihss", "卒中量表", "神经功能缺损评分", "gcs", "格拉斯哥"]),
    ("stroke_identification", ["卒中识别", "急性缺血性卒中", "脑梗死", "脑出血", "脑卒中", "ischemic stroke", "intracerebral hemorrhage", "脑梗"]),
]

# 临床阶段(phase)关键词
PHASE_RULES = [
    # (阶段, 关键词列表)
    ("acute", ["急性", "急诊", "急性期", "早期", "发病", "急性缺血性卒中", "溶栓", "取栓", "acute"]),
    ("secondary", ["二级预防", "康复", "随访", "长期", "复发预防", "secondary"]),
]

# 权威等级:按文档来源评分(5 最高)
AUTHORITY_BY_SOURCE = {
    "诊治指南": 5, "管理指南": 5, "治疗指南": 5, "防治指南": 5, "诊疗指南": 5,
    "专家共识": 4, "指导规范": 4, "防治规范": 4,
    "guidelines": 5, "ais": 5,
    "教材": 3, "textbook": 3,
}

# 干预(intervention)关键词 → 标签: 具体药物/操作, 用于干预级临床匹配
# 例如查询 "rt-PA 静脉溶栓" 应优先召回 intervention=alteplase 的 chunk
INTERVENTION_RULES = [
    ("alteplase", ["阿替普酶", "rt-pa", "rtpa", "alteplase", "组织型纤溶酶原激活剂", "tpa"]),
    ("tenecteplase", ["替奈普酶", "tnk", "tenecteplase"]),
    ("urokinase", ["尿激酶", "urokinase"]),
    ("mechanical_thrombectomy", ["取栓", "血管内治疗", "thrombectomy", "机械取栓", "evt", "支架取栓", "抽吸取栓"]),
    ("aspirin", ["阿司匹林", "aspirin"]),
    ("clopidogrel", ["氯吡格雷", "clopidogrel"]),
    ("ticagrelor", ["替格瑞洛", "ticagrelor"]),
    ("warfarin", ["华法林", "warfarin"]),
    ("rivaroxaban", ["利伐沙班", "rivaroxaban"]),
    ("dabigatran", ["达比加群", "dabigatran"]),
    ("heparin", ["肝素", "低分子肝素", "heparin", "enoxaparin", "依诺肝素"]),
    ("statin", ["他汀", "阿托伐他汀", "瑞舒伐他汀", "statin", "atorvastatin", "rosuvastatin", "ldl"]),
    ("bp_lowering", ["降压", "血压管理", "氨氯地平", "收缩压", "舒张压", "降压药物", "antihypertens"]),
    ("neuroprotectant", ["神经保护", "依达拉奉", "neuroprotect"]),
]

# 决策节点(decision_node)关键词 → 标签: 对齐 Decision Planner 的决策类型
# 例如 "IV thrombolysis" 决策应优先召回 decision_node=iv_thrombolysis 的 chunk
DECISION_NODE_RULES = [
    ("iv_thrombolysis", ["静脉溶栓", "阿替普酶", "rt-pa", "rtpa", "alteplase", "组织型纤溶酶原激活剂", "溶栓治疗", "tpa"]),
    ("mechanical_thrombectomy", ["取栓", "机械取栓", "血管内治疗", "thrombectomy", "evt", "支架取栓", "抽吸取栓"]),
    ("bp_management", ["血压管理", "降压治疗", "收缩压", "舒张压", "血压控制", "antihypertens"]),
    ("anticoagulation", ["抗凝治疗", "华法林", "利伐沙班", "达比加群", "低分子肝素", "anticoagulation", "doac", "novac"]),
    ("antiplatelet", ["抗血小板", "阿司匹林", "氯吡格雷", "替格瑞洛", "双抗", "antiplatelet", "aspirin", "clopidogrel"]),
    ("lipid_management", ["他汀", "降脂", "血脂管理", "阿托伐他汀", "瑞舒伐他汀", "statin", "lipid"]),
    ("secondary_prevention", ["二级预防", "卒中复发", "复发预防", "secondary prevention"]),
    ("lvo_detection", ["大血管闭塞", "cta", "ctp", "lvo", "血管成像", "闭塞评估", "large vessel"]),
    ("imaging_diagnosis", ["影像学", "头颅ct", "mri", "dwi", "aspects", "灌注", "imaging", "ct平扫"]),
    ("stroke_identification", ["卒中识别", "急性缺血性卒中", "脑梗死", "脑出血", "脑卒中", "ischemic stroke", "intracerebral hemorrhage"]),
]

# 证据等级(evidence_level)关键词: 仅证据等级形态(如 "A级证据"/"Level A")。
# 注意: 推荐等级(Ⅰ级推荐/Ⅱ级推荐/Class I)与证据等级(A/B/C级证据)是不同维度,
# 不可混入同一字段 —— "Ⅰ级推荐,B级证据" 应以 "B级证据" 为准。
EVIDENCE_LEVEL_RULES = [
    ("A", ["a级证据", "证据等级a", "a类证据", "level a"]),
    ("B", ["b级证据", "证据等级b", "b类证据", "level b"]),
    ("C", ["c级证据", "证据等级c", "c类证据", "level c"]),
]

# 时间窗(time_window)关键词: 溶栓/取栓时间窗等治疗时限
TIME_WINDOW_RULES = [
    ("0-4.5h", ["4.5小时", "4.5h", "4.5 小时", "4小时30分", "4.5 hours", "4.5-hour"]),
    ("0-3h", ["3小时", "3h", "3 小时", "三小时", "3 hours", "3-hour"]),
    ("0-6h", ["6小时", "6h", "6 小时", "六小时", "6 hours", "6-hour"]),
    ("0-24h", ["24小时", "24h", "24 小时", "二十四小时", "24 hours", "24-hour"]),
]


def time_window_hit(lower_text: str, kws) -> bool:
    """时间窗关键词匹配: 数字型关键词(3h/3小时/4.5h)加数字边界,
    避免 "13小时" 误中 "3小时"、"14.5h" 误中 "4.5h"。"""
    for kw in kws:
        kw_l = str(kw).lower()
        if re.search(r"[0-9]", kw_l):
            if re.search(r"(?<![0-9.])" + re.escape(kw_l) + r"(?![0-9.])", lower_text):
                return True
        elif kw_l in lower_text:
            return True
    return False


def _extract_year(filename: str) -> int | None:
    """从文件名提取年份(如 2023/2024)。"""
    m = re.search(r"(20\d{2})", filename)
    return int(m.group(1)) if m else None


def enrich_metadata(filename: str, page_text: str, category: str) -> Dict:
    """
    Evidence Metadata 增强:从文件名+内容关键词生成结构化标签。

    返回: source/category/evidence_type/topic/subtopic/phase/year/authority
    """
    lower_text = page_text.lower()
    lower_file = filename.lower()

    # subtopic:内容关键词命中(多个则取前 2)
    subtopics = []
    for label, kws in SUBTOPIC_RULES:
        if any(kw.lower() in lower_text for kw in kws):
            subtopics.append(label)
    if not subtopics:
        # 文件名兜底
        for label, kws in SUBTOPIC_RULES:
            if any(kw.lower() in lower_file for kw in kws):
                subtopics.append(label)

    # intervention:具体药物/操作(内容关键词命中, 取前 2)
    interventions = []
    for label, kws in INTERVENTION_RULES:
        if any(kw.lower() in lower_text for kw in kws):
            interventions.append(label)
    if not interventions:
        for label, kws in INTERVENTION_RULES:
            if any(kw.lower() in lower_file for kw in kws):
                interventions.append(label)

    # decision_node:临床决策节点(内容关键词命中, 取前 2)
    decision_nodes = []
    for label, kws in DECISION_NODE_RULES:
        if any(kw.lower() in lower_text for kw in kws):
            decision_nodes.append(label)
    if not decision_nodes:
        for label, kws in DECISION_NODE_RULES:
            if any(kw.lower() in lower_file for kw in kws):
                decision_nodes.append(label)

    # evidence_level:证据等级(内容关键词命中, 取第一个; 默认 "NA")
    evidence_level = "NA"
    for label, kws in EVIDENCE_LEVEL_RULES:
        if any(kw.lower() in lower_text for kw in kws):
            evidence_level = label
            break

    # time_window:治疗时间窗(内容关键词命中, 取前 2; 数字边界防子串误判)
    time_windows = []
    for label, kws in TIME_WINDOW_RULES:
        if time_window_hit(lower_text, kws):
            time_windows.append(label)
    if not time_windows:
        for label, kws in TIME_WINDOW_RULES:
            if time_window_hit(lower_file, kws):
                time_windows.append(label)

    # phase
    phase = "general"
    for p, kws in PHASE_RULES:
        if any(kw.lower() in lower_text for kw in kws):
            phase = p
            break

    # evidence_type:由 category 映射
    evidence_type = {
        "指南": "guideline",
        "专家共识": "consensus",
        "规范": "guideline",
        "教材": "textbook",
        "其他": "review",
    }.get(category, "review")

    # authority
    authority = 3
    for kw, score in AUTHORITY_BY_SOURCE.items():
        if kw.lower() in lower_file:
            authority = max(authority, score)

    return {
        "source": filename,
        "category": category,
        "evidence_type": evidence_type,
        # Chroma metadata 不支持 list → 逗号分隔字符串(读取时拆分)
        "subtopic": ",".join(subtopics[:2]),
        # 具体干预(药物/操作), 用于干预级临床匹配
        "intervention": ",".join(interventions[:2]),
        # 临床决策节点(对齐 Decision Planner 决策类型)
        "decision_node": ",".join(decision_nodes[:2]),
        # 证据等级(A/B/C, 无则 NA)
        "evidence_level": evidence_level,
        # 治疗时间窗(如 0-4.5h), 用于时限约束匹配
        "time_window": ",".join(time_windows[:2]),
        "phase": phase,
        # Chroma metadata 不接受 None → 无年份时用 0
        "year": _extract_year(filename) or 0,
        "authority": authority,
    }


def classify_document(filename: str) -> str:
    """根据文件名关键词将文档分类(指南/专家共识/规范/教材/其他)。"""
    lower = filename.lower()
    for category, keywords in CATEGORY_RULES:
        for kw in keywords:
            if kw.lower() in lower:
                return category
    return DEFAULT_CATEGORY

def clean_text(text: str) -> str:
    text = text.replace("\n", "").replace(" ", "")
    text = text.replace("，，", "，").replace("。。", "。")
    return text.strip()

def load_pdfs_from_dir(dir_path: str):
    documents = []
    if not os.path.exists(dir_path):
        logger.warning(f"⚠️ 文档目录不存在: {dir_path}")
        return []
    for filename in os.listdir(dir_path):
        if not filename.lower().endswith(".pdf"):
            continue
        pdf_path = os.path.join(dir_path, filename)
        category = classify_document(filename)
        logger.info(f"📄 加载 PDF: {filename} [类别: {category}]")
        try:
            # langchain-community 已 sunset: 改用 pypdf 直读(行为等价)
            # metadata["page"] 保持 0 基索引, 与旧 PyPDFLoader 语义一致(证据页码显示 p.{page+1})
            reader = PdfReader(pdf_path)
            for page_index, page in enumerate(reader.pages):
                text = page.extract_text() or ""
                cleaned = clean_text(text)
                if len(cleaned) < 50:
                    continue
                documents.append(Document(
                    page_content=cleaned,
                    metadata={
                        "source": filename,
                        "page": page_index,
                        "category": category,
                        # Evidence Metadata 增强
                        **enrich_metadata(filename, cleaned, category),
                    }
                ))
        except Exception as e:
            logger.error(f"❌ 加载 {filename} 失败: {e}")
    logger.info(f"✅ 共加载 {len(documents)} 页医学文档")
    return documents

# 语义分块参数(粗切 + 边界微调)
SEMANTIC_BREAK_PERCENTILE = 90      # 相似度低于该百分位视为语义断裂点(不合并)
SEMANTIC_MIN_CHUNK = 400            # 语义块最小字符数(过小则合并到相邻块)
SEMANTIC_MAX_CHUNK = 2400           # 语义块最大字符数(超过则强制分割)
SEMANTIC_BATCH = 20                 # embedding 批大小
COARSE_CHUNK_SIZE = 800             # 粗切窗口字符数
COARSE_OVERLAP = 100                # 粗切重叠字符数


def _embed_texts(texts):
    """批量获取文本 embedding(DashScope text-embedding-v2)。"""
    from app.rag.retrievers import DashScopeEmbeddings
    emb = DashScopeEmbeddings(model="text-embedding-v2")
    return np.array(emb.embed_documents(texts))


def _cosine_sim(a, b):
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))


# 语义分块结果缓存目录(避免每次启动重复 embedding)
_SEMANTIC_CACHE_DIR = os.environ.get(
    "SEMANTIC_CACHE_DIR",
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "model_cache", "semantic_chunks"),
)


def _semantic_cache_path(source: str) -> str:
    """计算某来源文档的语义分块缓存文件路径。"""
    safe_name = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]", "_", source)
    return os.path.join(_SEMANTIC_CACHE_DIR, f"{safe_name}.json")


def _load_semantic_cache(source: str) -> List[Dict] | None:
    """读取语义分块缓存;不存在或为空返回 None。"""
    path = _semantic_cache_path(source)
    try:
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list) and data:
            return data
    except Exception as e:
        logger.warning(f"⚠️  [语义分块缓存] 读取失败({e}), 重新分块")
    return None


def _save_semantic_cache(source: str, chunks: List[Dict]) -> None:
    """保存语义分块结果到磁盘缓存。"""
    try:
        os.makedirs(_SEMANTIC_CACHE_DIR, exist_ok=True)
        path = _semantic_cache_path(source)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(chunks, f, ensure_ascii=False)
        logger.info(f"💾 [语义分块缓存] 已保存 {len(chunks)} 块: {source[:40]}...")
    except Exception as e:
        logger.warning(f"⚠️  [语义分块缓存] 写入失败: {e}")


def semantic_split(documents, break_percentile=SEMANTIC_BREAK_PERCENTILE):
    """
    粗切 + 边界语义微调分块(适用于教材, 兼顾效率与语义完整性):
    1. 先用固定窗口粗切(COARSE_CHUNK_SIZE 字符/块, 带重叠)
    2. 对相邻粗切块做 embedding, 计算余弦相似度
    3. 相似度高的相邻块合并(语义连续); 相似度低的保持分割(语义断裂)
    4. 合并结果受 [min, max] 长度约束

    相比句子级 embedding(2.7万句), 只需对几百个粗切块做 embedding, 成本可控。
    """
    if not documents:
        return []

    result = []
    from collections import defaultdict
    by_source = defaultdict(list)
    for doc in documents:
        by_source[doc.metadata.get("source", "unknown")].append(doc)

    for source, docs in by_source.items():
        # 尝试命中缓存(教材分块结果持久化, 避免每次启动重复 embedding)
        cached = _load_semantic_cache(source)
        if cached:
            logger.info(f"💾 [语义分块] {source[:40]}... 命中缓存 {len(cached)} 块")
            for item in cached:
                meta = dict(item.get("metadata", {"source": source, "category": "教材"}))
                # 缓存可能缺新字段 → 用 enrich_metadata 补齐(基于 source 文件名+内容)
                if "subtopic" not in meta or "authority" not in meta:
                    enriched = enrich_metadata(
                        str(meta.get("source", source)),
                        str(item.get("page_content", "")),
                        str(meta.get("category", "教材")),
                    )
                    for k, v in enriched.items():
                        meta.setdefault(k, v)
                result.append(Document(
                    page_content=item.get("page_content", ""),
                    metadata=meta,
                ))
            continue

        full_text = "\n".join(d.page_content for d in docs)
        if len(full_text.strip()) < SEMANTIC_MIN_CHUNK:
            result.append(Document(
                page_content=full_text.strip(),
                metadata={"source": source, "page": docs[0].metadata.get("page", -1), "category": docs[0].metadata.get("category", ""), "chunk_type": "semantic"},
            ))
            continue

        # 1. 粗切:按字符窗口切分, 重叠 COARSE_OVERLAP
        coarse = _recursive_split_docs(
            [Document(page_content=full_text, metadata={"source": source})],
            chunk_size=COARSE_CHUNK_SIZE,
            chunk_overlap=COARSE_OVERLAP,
        )
        coarse_texts = [c.page_content for c in coarse]
        logger.info(f"🧠 [语义分块] {source}: 粗切 {len(coarse_texts)} 块, 计算相邻块语义相似度...")

        # 2. 对粗切块 embedding(分批)
        emb_all = []
        try:
            for i in range(0, len(coarse_texts), SEMANTIC_BATCH):
                emb_all.extend(_embed_texts(coarse_texts[i:i + SEMANTIC_BATCH]))
        except Exception as e:
            logger.warning(f"⚠️  [语义分块] embedding 失败({e}), 退回固定分块")
            return _recursive_split_docs(documents, 512, 128)

        emb_all = np.array(emb_all)

        # 3. 计算相邻块相似度, 确定合并边界
        sims = []
        for i in range(1, len(emb_all)):
            sims.append(_cosine_sim(emb_all[i - 1], emb_all[i]))

        if len(sims) >= 3:
            threshold = float(np.percentile(sims, break_percentile))
        else:
            threshold = 0.5
        logger.info(f"🧠 [语义分块] {source}: 相邻相似度中位 {np.median(sims):.3f}, 合并阈值 {threshold:.3f}")

        # 4. 合并:相似度 >= 阈值则合并相邻块(语义连续)
        merged = []
        current = coarse_texts[0]
        for i in range(1, len(coarse_texts)):
            if sims[i - 1] >= threshold and len(current) + len(coarse_texts[i]) <= SEMANTIC_MAX_CHUNK:
                current = current + coarse_texts[i]
            else:
                if len(current) >= SEMANTIC_MIN_CHUNK:
                    merged.append(current)
                else:
                    # 过小块合并到下一个(避免孤立碎片)
                    if i + 1 < len(coarse_texts):
                        coarse_texts[i] = current + coarse_texts[i]
                    else:
                        merged.append(current)
                current = coarse_texts[i]

        if current and current.strip():
            if len(current) < SEMANTIC_MIN_CHUNK and merged:
                merged[-1] = merged[-1] + current
            else:
                merged.append(current)

        logger.info(f"🧠 [语义分块] {source}: {len(coarse_texts)} 粗块 → {len(merged)} 语义块")
        cached_items = []
        for chunk_text in merged:
            if chunk_text.strip():
                meta = {
                    "source": source,
                    "page": docs[0].metadata.get("page", -1),
                    "category": docs[0].metadata.get("category", ""),
                    "chunk_type": "semantic",
                }
                result.append(Document(page_content=chunk_text.strip(), metadata=meta))
                cached_items.append({"page_content": chunk_text.strip(), "metadata": meta})
        _save_semantic_cache(source, cached_items)
    return result


def _recursive_split_docs(documents, chunk_size=512, chunk_overlap=128):
    """原来的固定窗口分块方式(指南/共识/规范)。"""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "。", "；", "\n", " ", ""]
    )
    return splitter.split_documents(documents)


# ---- 垃圾 chunk 过滤(参考文献页/碎片) ----
# 参考文献页特征: 密集的 [数字] / (年份) / Vol. / doi / PMID / 作者引用
# 注意 clean_text 去空格后 "et al." 变为 "etal.", 需兼容无空格形态
# 弱特征(正文也可能出现, 如 [12] 脚注引用) + 强特征(参考文献页专属, 正文几乎不出现)
REFERENCE_WEAK_PATTERNS = [
    r"\[\d{1,3}\]",               # [12]
    r"\(\d{4}\)",                 # (2019)
    r"\bvol\.?\s*\d+",            # Vol. 10
    r"\bdoi\s*[:：]?\s*10\.",     # doi: 10.
    r"\bpmid\s*[:：]?\s*\d+",     # PMID: 123
]
REFERENCE_STRONG_PATTERNS = [
    r"\bet\s*al\.?|\betal\.?",                          # et al. / etal.
    r"[A-Za-z]{2,}\s*,\s*[A-Za-z]{2,}\s*,\s*[A-Za-z]{2,}",  # 连续 ≥3 作者名
    r"\b(?:19|20)\d{2}\s*[A-Za-z]{0,8}\s*[;:]",         # 期刊年份页码 "1962Dec;85" / "2020;12"
]
# 强特征命中数 ≥ 该值 → 参考文献页(正文不会出现 etal./作者列表/年份页码)
REFERENCE_STRONG_MIN = 3
# 其中"期刊年份页码"标记至少出现次数(参考文献页必备, 正文几乎不出现
# "1962Dec;85" 形态), 避免把正文缩写列举("NIHSS,mRS,Barthel")
# 或英文正文的零星 "et al." 当参考文献页
REFERENCE_MARKER_MIN = 2
# 弱特征密度阈值(仅当强特征不足时兜底)
REFERENCE_DENSITY_THRESHOLD = 0.15
# 最短有效 chunk(字符), 过短碎片无信息量
MIN_CHUNK_CHARS = 100


def is_reference_chunk(text: str,
                       strong_min: int = REFERENCE_STRONG_MIN,
                       marker_min: int = REFERENCE_MARKER_MIN,
                       weak_threshold: float = REFERENCE_DENSITY_THRESHOLD) -> bool:
    """参考文献页判定:

    强特征组合计数: 总强特征(et al./作者列表/期刊年份页码)命中 ≥ strong_min,
    且其中真正的"引用标记"(et al. 或 期刊年份页码) ≥ marker_min, 才判定垃圾。
    这样正文缩写列举("NIHSS,mRS,Barthel")或英文正文零星 "et al." 不会被误删。
    强特征不足时用弱特征(引用标注 [12] 等)密度兜底。
    """
    if not text:
        return False
    n_etal = len(re.findall(r"\bet\s*al\.?|\betal\.?", text, re.IGNORECASE))
    n_authors = len(re.findall(r"[A-Za-z]{2,}\s*,\s*[A-Za-z]{2,}\s*,\s*[A-Za-z]{2,}",
                               text, re.IGNORECASE))
    n_year = len(re.findall(r"\b(?:19|20)\d{2}\s*[A-Za-z]{0,8}\s*[;:]",
                            text, re.IGNORECASE))
    # 参考文献页必备: 期刊年份页码标记 ≥2(正文几乎不出现 "1962Dec;85" 形态)
    # 且总强特征(含 et al./作者列表/年份页码) ≥ strong_min,
    # 避免英文正文零星 "et al."(无年份)或缩写列举被误删
    strong_total = n_etal + n_authors + n_year
    if strong_total >= strong_min and n_year >= marker_min:
        return True
    weak = sum(len(re.findall(p, text, re.IGNORECASE))
               for p in REFERENCE_WEAK_PATTERNS)
    if weak < 5:
        return False
    return (weak * 12) / max(len(text), 1) > weak_threshold


def _recompute_chunk_metadata(chunk: Document) -> None:
    """Chunk-level enrichment: 用 chunk 文本重算内容级标签。

    替换页面级关键词提取的继承标签(避免"整页含TOAST → 所有chunk都标toast"的
    误标传播); 保留 source/page/category 等页面级结构字段。
    重算字段: subtopic/decision_node/intervention/time_window/evidence_level/phase。
    """
    meta = chunk.metadata
    source = str(meta.get("source", "") or "")
    category = str(meta.get("category", "") or "")
    enriched = enrich_metadata(source, chunk.page_content, category)
    for key in ("subtopic", "decision_node", "intervention",
                "time_window", "evidence_level", "phase"):
        meta[key] = enriched.get(key, meta.get(key, ""))
    # year/authority 仍从文件名推导, 与页面级一致
    meta["year"] = enriched.get("year", meta.get("year", 0))
    meta["authority"] = enriched.get("authority", meta.get("authority", 3))


def split_documents(documents):
    if not documents:
        return []

    # 按类别分流:教材→语义分块; 指南/共识/规范→原固定窗口分块
    textbook_docs = [d for d in documents if d.metadata.get("category") == "教材"]
    guideline_docs = [d for d in documents if d.metadata.get("category") != "教材"]

    chunks = []
    if guideline_docs:
        chunks.extend(_recursive_split_docs(guideline_docs, 512, 128))
    if textbook_docs:
        logger.info(f"📚 教材类文档 {len(textbook_docs)} 页, 使用语义分块")
        chunks.extend(semantic_split(textbook_docs))

    # 垃圾过滤 + Chunk-level enrichment
    kept = []
    dropped_ref = dropped_short = 0
    for chunk in chunks:
        text = chunk.page_content.strip()
        if len(text) < MIN_CHUNK_CHARS:
            dropped_short += 1
            continue
        if is_reference_chunk(text):
            dropped_ref += 1
            continue
        _recompute_chunk_metadata(chunk)
        kept.append(chunk)

    logger.info(f"✂️  分块完成: 指南类 {len(guideline_docs)} 页 → 固定分块; "
                f"教材类 {len(textbook_docs)} 页 → 语义分块; "
                f"总 chunks={len(chunks)} → 有效 {len(kept)} "
                f"(丢弃: 引用页 {dropped_ref}, 过短 {dropped_short})")
    return kept

