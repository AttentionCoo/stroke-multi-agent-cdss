"""BM25 中文分词与中英混合检索测试，不依赖向量库或外部 API。"""

from app.rag.bm25 import BM25RetrieverCompat
from app.rag.bm25_tokenizer import jieba_bm25_tokenize, whitespace_bm25_tokenize


class SampleDocument:
    def __init__(self, page_content: str):
        self.page_content = page_content


def test_jieba_tokenizer_preserves_medical_and_mixed_language_terms():
    tokens = jieba_bm25_tokenize(
        "急性缺血性卒中发病4.5小时内使用阿替普酶静脉溶栓（rt-PA），NIHSS≥5，95%CI"
    )

    assert "急性缺血性卒中" in tokens
    assert "阿替普酶" in tokens
    assert "静脉溶栓" in tokens
    assert "rt-pa" in tokens
    assert "nihss" in tokens
    assert "4.5" in tokens
    assert "5" in tokens
    assert "95%ci" in tokens
    assert "4" not in tokens
    assert "5h" not in tokens


def test_bm25_retrieves_chinese_match_that_whitespace_tokenization_misses():
    documents = [
        SampleDocument("他汀类药物可用于缺血性卒中患者的二级预防。"),
        SampleDocument("大血管闭塞患者应评估机械取栓及血管内治疗。"),
        SampleDocument("阿替普酶静脉溶栓的治疗时间窗通常为发病后4.5小时内。"),
        SampleDocument("房颤相关卒中需评估抗凝治疗与出血风险。"),
    ]
    query = "阿替普酶静脉溶栓时间窗"

    jieba_result = BM25RetrieverCompat(documents, k=len(documents))
    legacy_result = BM25RetrieverCompat(
        documents, k=len(documents), tokenizer=whitespace_bm25_tokenize
    )

    assert jieba_result.invoke(query)[0] is documents[2]
    assert not legacy_result.invoke(query)


def test_index_and_query_share_the_same_tokenizer():
    document = SampleDocument("NIHSS评分达到5分的急性缺血性卒中患者。")
    retriever = BM25RetrieverCompat([document], k=1)

    assert retriever._corpus[0] == retriever.tokenizer(document.page_content)
    assert retriever.invoke("NIHSS评分 5 急性缺血性卒中") == [document]


def test_short_queries_match_long_medical_terms():
    documents = [
        SampleDocument("脑出血急诊评估。"),
        SampleDocument("机械取栓、静脉溶栓和抗凝治疗需依据临床证据。"),
        SampleDocument("急性缺血性卒中的病因分型。"),
    ]
    retriever = BM25RetrieverCompat(documents)

    for query in ("取栓", "溶栓", "抗凝"):
        assert retriever.invoke(query)[0] is documents[1]
    assert retriever.invoke("缺血性卒中")[0] is documents[2]


def test_empty_or_unmatched_corpus_returns_no_random_evidence():
    assert BM25RetrieverCompat([SampleDocument("!!!")]).invoke("溶栓") == []
    assert BM25RetrieverCompat([]).invoke("溶栓") == []
    retriever = BM25RetrieverCompat([SampleDocument("脑出血"), SampleDocument("失语")])
    assert retriever.invoke("阿替普酶") == []
    assert retriever.invoke("!!!") == []


def test_unicode_numbers_and_repeated_terms_remain_consistent():
    assert jieba_bm25_tokenize("ＮＩＨＳＳ１８ ４．５ｈ") == jieba_bm25_tokenize("NIHSS18 4.5h")
    assert jieba_bm25_tokenize("静脉溶栓，静脉溶栓").count("静脉溶栓") == 2
