"""检索来源身份规范化与覆盖指标，不依赖向量库或 LLM。"""

from __future__ import annotations

import math
import re
import unicodedata
from typing import Any, Iterable


_SOURCE_ALIASES = {
    "neuroanatomythroughclinicalcases,3e.pdf": "neuroanatomy_clinical_cases.pdf",
    "neuroanatomythroughclinicalcases,3e(halblumenfeld).pdf": "neuroanatomy_clinical_cases.pdf",
    "neuroanatomythroughclinicalcases,3e(halblumenfeld)(z-library.sk,1lib.sk,z-lib.sk).pdf":
        "neuroanatomy_clinical_cases.pdf",
}


def normalize_source(source: str) -> str:
    """规范化路径、中文空白及全角字符，以完整文件名匹配而非子串匹配。"""
    normalized = unicodedata.normalize("NFKC", str(source or "")).strip()
    basename = normalized.replace("\\", "/").rsplit("/", 1)[-1]
    compact = re.sub(r"\s+", "", basename).casefold()
    # 仅对当前第三版的已知文件名做别名，其他版次保持独立来源身份。
    return _SOURCE_ALIASES.get(compact, compact)


def split_sources(source: Any) -> list[str]:
    """仅在 PDF 后分隔 QA 多来源，保留单个文件名内部的逗号。"""
    if isinstance(source, (list, tuple, set)):
        return [part for item in source for part in split_sources(item)]
    text = str(source or "").strip()
    if not text:
        return []
    return [
        part.strip()
        for part in re.split(r"(?<=\.pdf)\s*[,，;；]\s*", text, flags=re.IGNORECASE)
        if part.strip()
    ]


def source_ids(source: Any) -> set[str]:
    return {normalize_source(item) for item in split_sources(source) if normalize_source(item)}


def retrieval_metrics(
    documents: Iterable[Any],
    expected: list[str],
    available_sources: set[str] | None = None,
) -> dict[str, Any]:
    """Recall 按独立来源覆盖；MRR 按条目排名；NDCG 每条新增来源增益封顶为 1。"""
    docs = list(documents)
    expected_ids = source_ids(expected)
    if not expected_ids:
        raise ValueError("评测用例必须声明非空 expected_source")
    first_ranks: dict[str, int | None] = dict.fromkeys(sorted(expected_ids))
    seen: set[str] = set()
    dcg = 0.0
    for rank, doc in enumerate(docs, start=1):
        matched = source_ids(doc.metadata.get("source")) & expected_ids
        newly_matched = matched - seen
        for source in newly_matched:
            first_ranks[source] = rank
        if rank <= 10 and newly_matched:
            # 多来源 QA 可以提高覆盖，但同一个结果只贡献一次二值排序增益。
            dcg += 1.0 / math.log2(rank + 1)
        seen.update(matched)

    metrics: dict[str, Any] = {}
    for k in (3, 5, 10):
        covered = sum(rank is not None and rank <= k for rank in first_ranks.values())
        metrics[f"recall_at_{k}"] = covered / len(expected_ids)
    hit_ranks = [rank for rank in first_ranks.values() if rank is not None]
    first_hit = min(hit_ranks) if hit_ranks else None
    metrics["mrr"] = 1.0 / first_hit if first_hit else 0.0
    idcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, min(len(expected_ids), 10) + 1))
    metrics["ndcg_at_10"] = dcg / idcg
    metrics["first_hit_rank"] = first_hit
    metrics["expected_source_ranks"] = first_ranks
    metrics["unhit_expected_sources"] = sorted(expected_ids - seen)
    metrics["missing_expected_sources"] = (
        sorted(expected_ids - available_sources) if available_sources is not None else []
    )
    return metrics
