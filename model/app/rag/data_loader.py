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
                result.append(Document(
                    page_content=item.get("page_content", ""),
                    metadata=item.get("metadata", {"source": source, "category": "教材"}),
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

