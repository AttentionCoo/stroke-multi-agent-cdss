"""基于 rank_bm25 的轻量 BM25 检索器。"""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

from rank_bm25 import BM25Okapi

from app.rag.bm25_tokenizer import jieba_bm25_tokenize, whitespace_bm25_tokenize


class BM25RetrieverCompat:
    """兼容 LangChain invoke 接口的 BM25 检索器。"""

    def __init__(
        self,
        documents: list[Any],
        k: int = 4,
        tokenizer: Callable[[str], list[str]] | None = None,
    ):
        self.docs = list(documents)
        self.k = k
        if tokenizer is None:
            tokenizers = {
                "jieba": jieba_bm25_tokenize,
                "whitespace": whitespace_bm25_tokenize,
            }
            tokenizer_name = os.getenv("BM25_TOKENIZER", "jieba").strip().lower()
            if tokenizer_name not in tokenizers:
                raise ValueError(
                    f"不支持的 BM25_TOKENIZER={tokenizer_name!r}，"
                    f"可选值: {', '.join(tokenizers)}"
                )
            tokenizer = tokenizers[tokenizer_name]
        self.tokenizer = tokenizer
        self._corpus = [tokenizer(doc.page_content) for doc in self.docs]
        self._term_sets = [set(tokens) for tokens in self._corpus]
        self._bm25 = BM25Okapi(self._corpus) if any(self._corpus) else None

    def invoke(self, query: str, **kwargs) -> list[Any]:
        limit = kwargs.get("k", self.k)
        if self._bm25 is None or not query or limit <= 0:
            return []
        tokens = self.tokenizer(query)
        if not tokens:
            return []
        scores = self._bm25.get_scores(tokens)
        # 小 collection 中 rank_bm25 可能把仅出现一次的词赋为 0；用词项
        # 覆盖数做稳定的次级排序，避免中文精准命中被任意并列结果淹没。
        query_terms = set(tokens)
        overlap = [len(query_terms.intersection(terms)) for terms in self._term_sets]
        top = sorted(
            (index for index in range(len(scores)) if overlap[index]),
            key=lambda index: (scores[index], overlap[index]),
            reverse=True,
        )[:limit]
        return [self.docs[index] for index in top]
