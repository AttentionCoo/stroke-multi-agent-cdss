def truncate_text(text: str, max_chars: int) -> str:
    if not text:
        return ""

    if len(text) <= max_chars:
        return text

    half = max_chars // 2

    return (
        text[:half]
        + f"\n\n... [已截断 {len(text) - max_chars} 字符] ...\n\n"
        + text[-half:]
    )


def format_numbered_questions(questions) -> str:
    """将用户原始问题格式化为稳定的编号清单。"""
    return "\n".join(
        f"{index}. {str(question).strip()}"
        for index, question in enumerate(questions or [], start=1)
        if str(question).strip()
    )
