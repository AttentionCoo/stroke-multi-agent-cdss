import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.rag.data_loader import load_pdfs_from_dir, split_documents
from app.rag.retrievers import build_or_load_vectorstore, HybridRetriever, CONFIG


def main():
    docs_dir = CONFIG.get("docs_dir", "./data/documents")

    docs = load_pdfs_from_dir(docs_dir)

    chunks = split_documents(docs)
    print(f"✂️ 切分得到 {len(chunks)} 个 chunk")

    vectordb = build_or_load_vectorstore(chunks, persist_dir=CONFIG["persist_dir"])

    retriever = HybridRetriever(vectordb, chunks, k=5)

    query = "脑梗死出血转化的处理原则是什么？"
    results = retriever.search(query, top_k_final=5)

    for i, doc in enumerate(results, 1):
        print(f"\n[{i}] ({doc.metadata['source']} - p{doc.metadata['page']})")
        print(doc.page_content[:300])


if __name__ == "__main__":
    main()
