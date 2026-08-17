"""DashScope 文本向量化(从 retrievers.py 拆出, 单一职责)。"""

import logging
import os
from http import HTTPStatus
from typing import List

import dashscope
from dotenv import load_dotenv
from langchain_core.embeddings import Embeddings

logger = logging.getLogger(__name__)


class DashScopeEmbeddings(Embeddings):
    """DashScope 文本向量 + 批量缓存(相同文本批不再重复调用 API)。"""

    # 缓存上限: 超过后整体清空(简单 LRU 近似, 避免内存无限增长)
    CACHE_MAX_ENTRIES = 512

    def __init__(self, model: str = "text-embedding-v2"):
        self.model = model
        # 防御性加载:确保任何初始化时机都能拿到 API key(不依赖模块导入顺序)
        load_dotenv()
        self.api_key = os.getenv("DASHSCOPE_API_KEY")
        if not self.api_key:
            logger.error("❌ DASHSCOPE_API_KEY 未设置,embedding 将失败")
            raise ValueError("DASHSCOPE_API_KEY 环境变量未设置")
        self._cache: dict = {}

    def _embed_batch(self, batch: List[str]) -> List[List[float]]:
        resp = dashscope.TextEmbedding.call(
            model=self.model,
            input=batch,
            api_key=self.api_key,
        )
        if resp.status_code != HTTPStatus.OK:
            raise ValueError(f"DashScope embedding 失败: {resp.code} - {resp.message}")
        return [item["embedding"] for item in resp.output["embeddings"]]

    def _cached_batch(self, batch: List[str]) -> List[List[float]]:
        key = tuple(batch)
        if key in self._cache:
            logger.debug("⚡ [EmbeddingCache] 命中 %d 条文本", len(batch))
            return self._cache[key]
        if len(self._cache) >= self.CACHE_MAX_ENTRIES:
            self._cache.clear()
            logger.info("🗑️ [EmbeddingCache] 缓存满(%d), 已清空", self.CACHE_MAX_ENTRIES)
        result = self._embed_batch(batch)
        self._cache[key] = result
        return result

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        result = []
        for i in range(0, len(texts), 25):
            batch = texts[i:i + 25]
            result.extend(self._cached_batch(batch))
        return result

    def embed_query(self, text: str) -> List[float]:
        return self._cached_batch([text])[0]

    def clear_cache(self):
        self._cache.clear()
