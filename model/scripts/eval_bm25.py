"""用同一 PDF 页语料离线对照空白分词与 jieba，不调用任何 API。"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MODEL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODEL_ROOT))

from pypdf import PdfReader  # noqa: E402

from app.evaluation.retrieval_metrics import (  # noqa: E402
    normalize_source,
    retrieval_metrics,
    source_ids,
    split_sources,
)
from app.rag.bm25 import BM25RetrieverCompat  # noqa: E402
from app.rag.bm25_tokenizer import (  # noqa: E402
    jieba_bm25_tokenize,
    whitespace_bm25_tokenize,
)


METRIC_NAMES = ("recall_at_3", "recall_at_5", "recall_at_10", "mrr", "ndcg_at_10")
EXPERIMENT_LIMITATION = (
    "这是 PDF 整页 BM25-only 分词对照实验，使用原始问题，不调用 API。"
    "未包含线上文档切块、查询改写、collection 路由、向量召回、RRF、重排或答案生成，"
    "不能视为完整 RAGAS 结果，也不能直接与已有混合检索基线比较。"
    "来源命中只验证文献覆盖，不证明检索页面的语义相关性或临床正确性。"
)


@dataclass(frozen=True)
class PageDocument:
    page_content: str
    metadata: dict[str, Any]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_json(value: Any) -> str:
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def load_pdf_pages(docs_dir: Path, min_chars: int = 50) -> tuple[list[PageDocument], list[dict[str, Any]]]:
    """沿用对照实验处理：去掉换行，保留空格，仅保留长度至少 50 的页。"""
    if not docs_dir.is_dir():
        raise ValueError(f"PDF 目录不存在：{docs_dir}")
    paths = sorted(
        (path for path in docs_dir.iterdir() if path.is_file() and path.suffix.lower() == ".pdf"),
        key=lambda path: (normalize_source(path.name), path.name),
    )
    if not paths:
        raise ValueError(f"PDF 目录为空：{docs_dir}")
    documents: list[PageDocument] = []
    files: list[dict[str, Any]] = []
    for path in paths:
        reader = PdfReader(str(path))
        kept = 0
        for page_number, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").replace("\n", "").replace("\r", "")
            if len(text) >= min_chars:
                documents.append(PageDocument(text, {"source": path.name, "page": page_number}))
                kept += 1
        files.append({
            "name": path.name,
            "normalized_source": normalize_source(path.name),
            "sha256": sha256_file(path),
            "page_count": len(reader.pages),
            "retained_page_count": kept,
        })
    if not documents:
        raise ValueError("PDF 均未提取到符合长度条件的文本页，无法进行有效对照")
    return documents, files


def load_cases(cases_path: Path) -> list[dict[str, Any]]:
    cases = json.loads(cases_path.read_text(encoding="utf-8-sig"))
    if not isinstance(cases, list) or not cases:
        raise ValueError("题集必须是非空 JSON 数组")
    ids: set[str] = set()
    for case in cases:
        if not isinstance(case, dict) or not str(case.get("id") or "").strip():
            raise ValueError("每个用例必须有非空 id")
        if case["id"] in ids:
            raise ValueError(f"用例 id 重复：{case['id']}")
        ids.add(case["id"])
        if not str(case.get("question") or "").strip() or not source_ids(case.get("expected_source")):
            raise ValueError(f"用例 {case['id']} 缺少问题或 expected_source")
    return cases


def run_comparison(
    documents: list[PageDocument], cases: list[dict[str, Any]], top_k: int = 20,
) -> dict[str, Any]:
    if top_k < 10:
        raise ValueError("top_k 至少为 10，才能完整计算 Recall@10 和 NDCG@10")
    if not documents or not cases:
        raise ValueError("语料和题集都不能为空")
    available_sources = set().union(*(source_ids(doc.metadata.get("source")) for doc in documents))
    results: dict[str, Any] = {}
    for name, tokenizer in (
        ("whitespace", whitespace_bm25_tokenize), ("jieba", jieba_bm25_tokenize),
    ):
        retriever = BM25RetrieverCompat(documents, k=top_k, tokenizer=tokenizer)
        per_case = []
        for case in cases:
            ranked = retriever.invoke(case["question"])
            metrics = retrieval_metrics(ranked, case["expected_source"], available_sources)
            per_case.append({
                "id": case["id"],
                "question": case["question"],
                "case_sha256": sha256_json(case),
                "expected_sources": sorted(source_ids(case["expected_source"])),
                **metrics,
                "ranking": [{"rank": rank, **doc.metadata} for rank, doc in enumerate(ranked, start=1)],
            })
        results[name] = {
            "metrics": {key: sum(case[key] for case in per_case) / len(per_case) for key in METRIC_NAMES},
            "unhit_case_ids": [case["id"] for case in per_case if case["first_hit_rank"] is None],
            "cases": per_case,
        }
    return {
        "tokenizers": results,
        "delta_jieba_minus_whitespace": {
            key: results["jieba"]["metrics"][key] - results["whitespace"]["metrics"][key]
            for key in METRIC_NAMES
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    data = report["dataset"]
    lines = [
        "# BM25 分词离线对照报告", "",
        EXPERIMENT_LIMITATION, "",
        f"- 生成时间：{report['generated_at']}",
        f"- PDF：{data['pdf_count']} 份；保留页：{data['retained_page_count']}；题数：{data['case_count']}",
        f"- 题集文件 SHA-256：`{data['benchmark_file_sha256']}`",
        f"- PDF 清单 SHA-256：`{data['pdf_manifest_sha256']}`",
        f"- 页语料 SHA-256：`{data['corpus_sha256']}`",
        f"- 每题最多返回 {report['settings']['top_k']} 页，缺失预期来源仍计入指标分母。", "",
        "| 指标 | 空白分词 | jieba | 绝对变化 |", "|---|---:|---:|---:|",
    ]
    for key in METRIC_NAMES:
        old = report["tokenizers"]["whitespace"]["metrics"][key]
        new = report["tokenizers"]["jieba"]["metrics"][key]
        lines.append(f"| {key} | {old:.4f} | {new:.4f} | {new - old:+.4f} |")
    for tokenizer, result in report["tokenizers"].items():
        lines += ["", f"## {tokenizer} 逐题结果", "",
                  "| 用例 | R@3 | R@5 | R@10 | MRR | NDCG@10 | 首命中 | 未命中来源 | 语料缺失来源 |",
                  "|---|---:|---:|---:|---:|---:|---:|---|---|"]
        for case in result["cases"]:
            values = " | ".join(f"{case[key]:.4f}" for key in METRIC_NAMES)
            unhit = ", ".join(case["unhit_expected_sources"]) or "无"
            missing = ", ".join(case["missing_expected_sources"]) or "无"
            lines.append(f"| {case['id']} | {values} | {case['first_hit_rank'] or '未命中'} | {unhit} | {missing} |")
        lines += ["", "### 各题页排名", ""]
        for case in result["cases"]:
            ranking = "；".join(f"{item['rank']}. {item['source']} p.{item['page']}" for item in case["ranking"])
            lines.append(f"- {case['id']}：{ranking or '无匹配页'}")
    lines += ["", "## PDF 文件溯源", "", "| 文件 | SHA-256 | 总页数 | 保留页数 |", "|---|---|---:|---:|"]
    for file in data["pdf_files"]:
        lines.append(f"| {file['name']} | `{file['sha256']}` | {file['page_count']} | {file['retained_page_count']} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="零 API 调用的 PDF 页 BM25 分词对照评测")
    parser.add_argument("--docs-dir", type=Path, default=MODEL_ROOT / "data" / "documents")
    parser.add_argument("--cases", type=Path, default=MODEL_ROOT / "evaluation" / "stroke_ragas.json")
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--output", type=Path, required=True, help="JSON 输出路径，同时生成同名 Markdown")
    args = parser.parse_args(argv)
    if args.top_k < 10:
        parser.error("--top-k 至少为 10")
    if args.output.suffix.lower() != ".json":
        parser.error("--output 必须是 .json 文件路径")
    cases = load_cases(args.cases)
    documents, files = load_pdf_pages(args.docs_dir)
    report = {
        "experiment": "pdf_page_bm25_tokenizer_ab",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "limitation": EXPERIMENT_LIMITATION,
        "api_calls": 0,
        "settings": {
            "top_k": args.top_k,
            "min_page_chars": 50,
            "preprocessing": "删除 CR/LF，保留空格",
            "query": "原始问题，不进行翻译或改写",
            "retrieval": "两个 tokenizer 显式传给同一个 BM25RetrieverCompat，使用其相同排序和过滤规则",
        },
        "versions": {name: importlib.metadata.version(name) for name in ("jieba", "rank-bm25", "pypdf")},
        "implementation_sha256": {
            "eval_bm25.py": sha256_file(Path(__file__)),
            "retrieval_metrics.py": sha256_file(MODEL_ROOT / "app" / "evaluation" / "retrieval_metrics.py"),
            **{
                name: sha256_file(MODEL_ROOT / "app" / "rag" / name)
                for name in ("bm25.py", "bm25_tokenizer.py")
            },
        },
        "dataset": {
            "docs_dir": str(args.docs_dir.resolve()),
            "cases_path": str(args.cases.resolve()),
            "pdf_count": len(files),
            "case_count": len(cases),
            "retained_page_count": len(documents),
            "benchmark_file_sha256": sha256_file(args.cases),
            "cases_sha256": sha256_json(cases),
            "pdf_manifest_sha256": sha256_json(files),
            "corpus_sha256": sha256_json([{"text": doc.page_content, **doc.metadata} for doc in documents]),
            "pdf_files": files,
        },
        **run_comparison(documents, cases, args.top_k),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.output.with_suffix(".md").write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps({name: result["metrics"] for name, result in report["tokenizers"].items()}, ensure_ascii=False, indent=2))
    print(f"离线对照报告：{args.output.resolve()}；{args.output.with_suffix('.md').resolve()}")


if __name__ == "__main__":
    main()
