import os
import json
import logging
import re
from typing import Dict, List
import numpy as np
from langchain_community.document_loaders import PyPDFLoader
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
        "phase": phase,
        "year": _extract_year(filename),
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
            loader = PyPDFLoader(pdf_path)
            pages = loader.load()
            for page in pages:
                cleaned = clean_text(page.page_content)
                if len(cleaned) < 50:
                    continue
                documents.append(Document(
                    page_content=cleaned,
                    metadata={
                        "source": filename,
                        "page": page.metadata.get("page", -1),
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

    logger.info(f"✂️  分块完成: 指南类 {len(guideline_docs)} 页 → 固定分块; 教材类 {len(textbook_docs)} 页 → 语义分块; 总 chunks={len(chunks)}")
    return chunks

