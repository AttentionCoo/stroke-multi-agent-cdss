"""只读检查持久化片段的词项频率与 BM25 候选，不调用 API。"""

import json
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.rag.bm25 import BM25RetrieverCompat
from app.rag.bm25_tokenizer import jieba_bm25_tokenize
from scripts.eval_bm25 import PageDocument


model_root = Path(__file__).resolve().parents[1]
database = model_root / "model_cache" / "rag_ab_20261014" / "chroma_db_unified" / "chroma.sqlite3"
connection = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)
rows = connection.execute("""
    SELECT e.id, c.name, m.key, m.string_value, m.int_value, m.float_value, m.bool_value
    FROM embeddings e
    JOIN segments s ON s.id = e.segment_id
    JOIN collections c ON c.id = s.collection
    JOIN embedding_metadata m ON m.id = e.id
    ORDER BY e.id, m.key
""").fetchall()
raw = defaultdict(dict)
collections = {}
for identifier, collection, key, *values in rows:
    raw[identifier][key] = next((value for value in values if value is not None), None)
    collections[identifier] = collection
documents = defaultdict(list)
for identifier, metadata in raw.items():
    text = metadata.pop("chroma:document", "")
    if text:
        documents[collections[identifier]].append(PageDocument(text, metadata))

old = json.loads((model_root / "evaluation" / "retrieval_whitespace_20261014.json").read_text(encoding="utf-8"))
new = json.loads((model_root / "evaluation" / "retrieval_jieba_20261014.json").read_text(encoding="utf-8"))
benchmark = json.loads((model_root / "evaluation" / "stroke_ragas.json").read_text(encoding="utf-8"))
case_types = {case["id"]: case["evidence_type"] for case in benchmark}
lookup = {case["id"]: case for case in new["results"]}
changed = [case for case in old["results"] if any(
    case[key] != lookup[case["id"]][key] for key in ("recall@3", "recall@10", "mrr")
)]
retrievers = {name: BM25RetrieverCompat(docs, tokenizer=jieba_bm25_tokenize, k=8) for name, docs in documents.items()}
result = {}
for case in changed:
    evidence_type = case_types[case["id"]]
    collection_names = (
        ["guideline_collection", "etiology_collection"] if evidence_type == "diagnosis"
        else [f"{evidence_type}_collection"]
    )
    per_collection = {}
    for name in collection_names:
        retriever = retrievers[name]
        frequency = Counter(term for terms in retriever._term_sets for term in terms)
        per_collection[name] = {
            "document_count": len(retriever.docs),
            "query_terms": [{"term": term, "df": frequency[term], "df_ratio": round(frequency[term] / len(retriever.docs), 3)}
                            for term in dict.fromkeys(jieba_bm25_tokenize(case["retrieval_query"]))],
            "bm25_top8": [{"source": doc.metadata.get("source"), "page": doc.metadata.get("page"),
                            "intervention": doc.metadata.get("intervention"), "decision_node": doc.metadata.get("decision_node"),
                            "evidence_level": doc.metadata.get("evidence_level"), "year": doc.metadata.get("year"),
                            "clinical_intent": doc.metadata.get("clinical_intent"), "preview": doc.page_content[:180]}
                           for doc in retriever.invoke(case["retrieval_query"])],
        }
    result[case["id"]] = {"query": case["retrieval_query"], "collections": per_collection}
print(json.dumps(result, ensure_ascii=False, indent=2))
