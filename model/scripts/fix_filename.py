"""在容器/本地修复含 U+2026 文件名的 PDF(重命名为 ...)"""
import os

DOCS_DIR = "/app/data/documents"  # 容器内路径
if not os.path.isdir(DOCS_DIR):
    DOCS_DIR = "data/documents"   # 本地路径

for fn in os.listdir(DOCS_DIR):
    if not fn.lower().endswith(".pdf"):
        continue
    if "\u2026" in fn:
        new_name = fn.replace("\u2026", "...")
        src = os.path.join(DOCS_DIR, fn)
        dst = os.path.join(DOCS_DIR, new_name)
        os.rename(src, dst)
        print(f"重命名: {fn[:50]}... -> {new_name[:50]}...")
    elif "Guidelines" in fn:
        print(f"无需修复: {fn[:60]}")

print("完成")
