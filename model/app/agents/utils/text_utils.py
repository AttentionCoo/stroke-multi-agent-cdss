# 文本工具：截断与编号格式化，供检索/报告节点控制输出长度与展示格式。
def truncate_text(text: str, max_chars: int) -> str:
    # 超长文本采用"保留首尾、中间省略"的截断策略，避免丢掉结论的开头与结尾
    if not text:
        return ""

    if len(text) <= max_chars:
        return text

    # 首尾各保留一半额度，中间插入截断提示
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
