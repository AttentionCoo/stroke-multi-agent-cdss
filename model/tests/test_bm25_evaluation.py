"""BM25 页语料对照评测的来源计分与复现规则。"""

import json
import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.eval_bm25 import (
    PageDocument,
    load_cases,
    load_pdf_pages,
    main,
    normalize_source,
    retrieval_metrics,
    run_comparison,
    split_sources,
)


def doc(source, text="文本", page=1):
    return PageDocument(text, {"source": source, "page": page})


def test_source_normalization_ignores_paths_spaces_and_full_width_punctuation():
    assert normalize_source(r"D:\目录\脑血管病防治指南（2024 年版）.pdf") == normalize_source(
        "脑血管病防治指南(2024年版).pdf"
    )
    assert normalize_source("Neuroanatomy through Clinical Cases, 3e (Hal Blumenfeld).pdf") == normalize_source(
        "neuroanatomy_clinical_cases.pdf"
    )
    assert normalize_source("卒中指南2023.pdf") != normalize_source("卒中指南2023更新版.pdf")


def test_multi_source_split_preserves_commas_inside_pdf_filename():
    textbook = "Neuroanatomy through Clinical Cases, 3e (Hal Blumenfeld).pdf"
    assert split_sources(textbook + ", 指南.pdf") == [textbook, "指南.pdf"]
    assert split_sources("指南.PDF，规范.pdf") == ["指南.PDF", "规范.pdf"]


def test_textbook_alias_does_not_merge_different_editions():
    second = "Neuroanatomy through Clinical Cases, 2e.pdf"
    third = "Neuroanatomy through Clinical Cases, 3e.pdf"
    assert normalize_source(second) != normalize_source(third)
    metrics = retrieval_metrics([doc(second)], [second, third])
    assert metrics["recall_at_3"] == 0.5
    assert metrics["ndcg_at_10"] < 1.0


def test_recall_counts_expected_identities_once_and_tracks_absent_sources():
    result = retrieval_metrics(
        [doc("无关.pdf"), doc("指南 2023.pdf"), doc("路径/指南2023.pdf"), doc("指南2023.pdf")],
        ["指南2023.pdf", "指南 2023.pdf", "共识.pdf"],
        {normalize_source("指南2023.pdf"), normalize_source("无关.pdf")},
    )
    assert result["recall_at_3"] == result["recall_at_5"] == result["recall_at_10"] == 0.5
    assert result["mrr"] == 0.5
    assert result["first_hit_rank"] == 2
    assert result["expected_source_ranks"] == {"共识.pdf": None, "指南2023.pdf": 2}
    assert result["missing_expected_sources"] == result["unhit_expected_sources"] == ["共识.pdf"]
    assert result["ndcg_at_10"] == pytest.approx((1 / math.log2(3)) / (1 + 1 / math.log2(3)))


def test_qa_multi_source_covers_both_expected_but_ndcg_gain_is_capped():
    result = retrieval_metrics(
        [doc("指南.pdf, 共识.pdf"), doc("指南.pdf"), doc("共识.pdf")],
        ["指南.pdf", "共识.pdf"],
    )
    assert result["recall_at_3"] == 1.0
    assert result["mrr"] == 1.0
    assert result["ndcg_at_10"] == pytest.approx(1 / (1 + 1 / math.log2(3)))
    assert result["unhit_expected_sources"] == []


def test_empty_results_are_zero_with_explicit_unhit_sources():
    result = retrieval_metrics([], ["指南.pdf"], set())
    assert result["first_hit_rank"] is None
    assert all(result[name] == 0 for name in ("recall_at_3", "recall_at_5", "recall_at_10", "mrr", "ndcg_at_10"))
    assert result["missing_expected_sources"] == result["unhit_expected_sources"] == ["指南.pdf"]
    with pytest.raises(ValueError, match="expected_source"):
        retrieval_metrics([], [])


def test_load_pages_removes_newlines_but_keeps_spaces_and_discards_short_pages(tmp_path, monkeypatch):
    path = tmp_path / "指南.pdf"
    path.write_bytes(b"synthetic-pdf")

    class Page:
        def __init__(self, text):
            self.text = text

        def extract_text(self):
            return self.text

    class Reader:
        def __init__(self, _path):
            self.pages = [Page("AB CD\n" * 10), Page("短"), Page(None)]

    monkeypatch.setattr("scripts.eval_bm25.PdfReader", Reader)
    pages, files = load_pdf_pages(tmp_path)
    assert len(pages) == 1
    assert pages[0].page_content == "AB CD" * 10
    assert pages[0].metadata["page"] == 1
    assert files[0]["page_count"] == 3
    assert files[0]["retained_page_count"] == 1
    assert len(files[0]["sha256"]) == 64


def test_comparison_is_repeatable_and_always_uses_both_explicit_tokenizers(monkeypatch):
    monkeypatch.setenv("BM25_TOKENIZER", "invalid_unused_environment")
    pages = [
        doc("血脂.pdf", "血脂管理他汀治疗目标"),
        doc("溶栓.pdf", "阿替普酶静脉溶栓时间窗"),
        doc("影像.pdf", "大脑中动脉闭塞影像筛选"),
        doc("量表.pdf", "NIHSS评分评估内容"),
    ]
    cases = [{"id": "t1", "question": "阿替普酶静脉溶栓的时间窗是多少？", "expected_source": ["溶栓.pdf"]}]
    result = run_comparison(pages, cases)
    assert result == run_comparison(pages, cases)
    assert set(result["tokenizers"]) == {"whitespace", "jieba"}
    assert result["tokenizers"]["jieba"]["cases"][0]["first_hit_rank"] == 1
    assert len(result["tokenizers"]["jieba"]["cases"][0]["case_sha256"]) == 64
    with pytest.raises(ValueError, match="top_k"):
        run_comparison(pages, cases, top_k=3)


def test_invalid_benchmark_has_no_silent_fallback(tmp_path):
    path = tmp_path / "cases.json"
    path.write_text(json.dumps([{"id": "t1", "question": "问题", "expected_source": []}]), encoding="utf-8")
    with pytest.raises(ValueError, match="expected_source"):
        load_cases(path)
    with pytest.raises(FileNotFoundError):
        load_cases(tmp_path / "missing.json")


def test_command_writes_json_and_markdown_to_requested_location(tmp_path, monkeypatch):
    cases_path = tmp_path / "cases.json"
    cases_path.write_text(json.dumps([
        {"id": "t1", "question": "静脉溶栓时间窗", "expected_source": ["指南.pdf"]}
    ]), encoding="utf-8")
    pages = [doc("指南.pdf", "静脉溶栓时间窗"), doc("血脂.pdf", "血脂管理他汀")]
    files = [{"name": "指南.pdf", "sha256": "0" * 64, "page_count": 1, "retained_page_count": 1}]
    monkeypatch.setattr("scripts.eval_bm25.load_pdf_pages", lambda _path: (pages, files))
    output = tmp_path / "reports" / "comparison.json"

    main(["--cases", str(cases_path), "--output", str(output)])

    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["api_calls"] == 0
    assert report["dataset"]["case_count"] == 1
    assert len(report["dataset"]["benchmark_file_sha256"]) == 64
    assert len(report["implementation_sha256"]["eval_bm25.py"]) == 64
    assert "不能视为完整 RAGAS" in output.with_suffix(".md").read_text(encoding="utf-8")
