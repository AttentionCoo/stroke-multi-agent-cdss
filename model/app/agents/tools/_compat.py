"""工具实现适配器

langchain 的 StructuredTool 以字段 kwargs 调用 func,而我们的实现函数
以 pydantic 模型实例为入参。本模块提供统一适配,保持领域实现简洁。
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Type

from pydantic import BaseModel


def model_func(
    schema: Type[BaseModel],
    impl: Callable[[BaseModel], Dict[str, Any]],
) -> Callable[..., Dict[str, Any]]:
    """将接收 pydantic 模型实例的实现函数适配为接收字段 kwargs 的 langchain 工具函数。"""

    def _wrapper(**kwargs: Any) -> Dict[str, Any]:
        return impl(schema(**kwargs))

    _wrapper.__name__ = impl.__name__
    _wrapper.__doc__ = impl.__doc__
    return _wrapper
