"""BM25 的中英混合分词，供文档建索引和查询共用。"""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

import jieba


# 医学术语词典降低默认分词对临床专名的切分差异。
_MEDICAL_TERMS = (
    "急性缺血性卒中",
    "缺血性脑卒中",
    "缺血性卒中",
    "脑梗死",
    "脑卒中",
    "大脑中动脉",
    "大脑前动脉",
    "大脑后动脉",
    "静脉溶栓",
    "阿替普酶",
    "尿激酶",
    "机械取栓",
    "取栓",
    "溶栓",
    "卒中",
    "血管内治疗",
    "血管再通",
    "抗血小板",
    "抗凝治疗",
    "抗凝",
    "心源性栓塞",
    "大动脉粥样硬化",
    "小动脉闭塞",
    "时间窗",
    "适应证",
    "禁忌证",
    "发病时间",
    "再灌注治疗",
    "出血转化",
    "血压控制",
    "TOAST分型",
    "NIHSS评分",
    "改良Rankin量表",
    "ASPECTS评分",
)

# 数字小数与临床单位作为完整词项处理，避免 4.5 被拆成 4 和 5。
_TEXT_SPAN = re.compile(
    r"[\u4e00-\u9fff]+|[a-z]+[a-z0-9]*(?:[-/][a-z0-9]+)*"
    r"|\d+(?:\.\d+)?(?:%[a-z]*|[a-z]+(?:/[a-z]+)?)?"
)
_CHINESE_SPAN = re.compile(r"[\u4e00-\u9fff]+\Z")
_NUMBER = re.compile(r"\d+(?:\.\d+)?")


@lru_cache(maxsize=1)
def _medical_tokenizer() -> jieba.Tokenizer:
    """独立词典实例，避免改变项目其他模块使用的全局 jieba 词典。"""
    tokenizer = jieba.Tokenizer()
    for term in _MEDICAL_TERMS:
        tokenizer.add_word(term.lower())
    return tokenizer


def jieba_bm25_tokenize(text: str) -> list[str]:
    """切分中文医学词语，同时保留英文缩写和数字表达。"""
    normalized = unicodedata.normalize("NFKC", str(text or "")).casefold()
    tokenizer = _medical_tokenizer()
    tokens: list[str] = []

    for span in _TEXT_SPAN.findall(normalized):
        if _CHINESE_SPAN.fullmatch(span):
            for word in tokenizer.lcut(span, HMM=False):
                parts = tokenizer.lcut_for_search(word, HMM=False)
                # 搜索模式只补 2/3 字子词；医学长词还需补更长的专名。
                parts.extend(
                    term.lower() for term in _MEDICAL_TERMS
                    if term.lower() in word and term.lower() not in parts
                )
                tokens.extend(parts)
        else:
            tokens.append(span)
            # NIHSS18/4.5h 同时可由 NIHSS、18、4.5 单独检索。
            parts = _NUMBER.findall(span)
            parts.extend(re.findall(r"[a-z]+", span))
            tokens.extend(dict.fromkeys(part for part in parts if part != span))

    return tokens


def whitespace_bm25_tokenize(text: str) -> list[str]:
    """保留旧版空白分词，供 A/B 评测对照使用。"""
    return str(text).lower().split()
