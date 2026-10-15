"""检索评测必须拒绝无效参数、空题集和部分 BM25 降级。"""

import sys
from types import SimpleNamespace

import pytest

from scripts import eval_ragas


@pytest.mark.parametrize("arguments", [
    ["--max-cases", "-1"], ["--top-k", "3"],
    ["--rerank-k", "9"], ["--candidate-k", "10", "--rerank-k", "12"],
])
def test_invalid_parameters_fail_before_initializing_retrieval(monkeypatch, arguments):
    monkeypatch.setattr(sys, "argv", ["eval_ragas", *arguments])
    monkeypatch.setattr(eval_ragas, "UnifiedSearchEngine", lambda **kwargs: pytest.fail("不应初始化"))
    with pytest.raises(SystemExit) as error:
        eval_ragas.main()
    assert error.value.code == 2


def test_missing_benchmark_does_not_substitute_fallback_cases(tmp_path):
    with pytest.raises(FileNotFoundError):
        eval_ragas.load_benchmark(tmp_path / "missing.json")


def test_partial_bm25_failure_rejects_tokenizer_comparison(monkeypatch):
    stores = {
        key: SimpleNamespace(_collection=SimpleNamespace(count=lambda: 1))
        for key in ("treatment", "anatomy")
    }
    engine = SimpleNamespace(
        collections=stores,
        retrievers={
            "treatment": SimpleNamespace(bm25=SimpleNamespace(docs=[object()])),
            "anatomy": SimpleNamespace(bm25=None),
        },
    )
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-unused-key")
    monkeypatch.setattr(sys, "argv", ["eval_ragas", "--retrieval-only"])
    monkeypatch.setattr(eval_ragas, "load_benchmark", lambda _path: [{}])
    monkeypatch.setattr(eval_ragas, "UnifiedSearchEngine", lambda **kwargs: engine)
    with pytest.raises(SystemExit) as error:
        eval_ragas.main()
    assert error.value.code == 3
