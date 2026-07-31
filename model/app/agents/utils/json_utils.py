"""模型结构化输出解析工具。"""

import json
from typing import Any


def parse_json_output(text: str, default: Any = None) -> Any:
    """兼容纯 JSON、Markdown 代码块和前后带说明文字的模型输出。"""
    content = (text or "").strip()
    if not content:
        return default

    try:
        return json.loads(content)
    except (TypeError, ValueError):
        pass

    for marker in ("```json", "```"):
        if marker not in content:
            continue
        try:
            candidate = content.split(marker, 1)[1].split("```", 1)[0].strip()
            return json.loads(candidate)
        except (IndexError, TypeError, ValueError):
            pass

    for start_char, end_char in (("{", "}"), ("[", "]")):
        start = content.find(start_char)
        end = content.rfind(end_char)
        if start == -1 or end <= start:
            continue
        try:
            return json.loads(content[start:end + 1])
        except (TypeError, ValueError):
            pass

    return default
