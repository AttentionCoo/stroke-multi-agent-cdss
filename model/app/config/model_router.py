"""多模型路由器(阶段4 多模型解耦)。

按角色(main/fast/turbo/consensus)从 models.yaml 读取模型配置并构建 ChatOpenAI 实例:
- 同角色实例复用(缓存), 避免重复创建连接池;
- 环境变量 MODEL_<ROLE> 覆盖默认型号, 支持不重建镜像切换模型;
- 兼容旧环境变量 CONSENSUS_MODEL(共识角色);
- 配置缺失时回退内置默认(main/fast/consensus=qwen-plus, turbo=qwen-turbo)。
"""

import os
import logging
from typing import Dict

from langchain_openai import ChatOpenAI

from app.config.config_loader import _load_yaml

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
_DEFAULT_API_KEY_ENV = "DASHSCOPE_API_KEY"
_DEFAULT_MODELS = {
    "main": "qwen-turbo",
    "fast": "qwen-turbo",
    "turbo": "qwen-turbo",
    "consensus": "qwen-turbo",
}
# 旧环境变量兼容(阶段3 之前只有 CONSENSUS_MODEL 可覆盖)
_LEGACY_ENV_OVERRIDES = {"consensus": "CONSENSUS_MODEL"}


class ModelRouter:
    """按角色解析并缓存 LLM 实例。"""

    def __init__(self, config_file: str = "models.yaml", usage_handler=None):
        self._data = _load_yaml(config_file)
        self._usage_handler = usage_handler
        self._clients: Dict[str, ChatOpenAI] = {}

    def resolve_model(self, role: str) -> str:
        """解析角色最终使用的型号(含环境变量覆盖), 不创建实例。"""
        cfg = self._role_config(role)
        # 优先级: yaml env_override(如 MODEL_CONSENSUS) > 旧兼容变量(如 CONSENSUS_MODEL) > yaml model > 内置默认
        env_names = [cfg.get("env_override", ""), _LEGACY_ENV_OVERRIDES.get(role, "")]
        for env_name in [n for n in env_names if n]:
            env_val = os.getenv(env_name, "").strip()
            if env_val:
                return env_val
        model = str(cfg.get("model", "") or "").strip()
        return model or _DEFAULT_MODELS.get(role, "qwen-plus")

    def get_llm(self, role: str) -> ChatOpenAI:
        """构建(或复用)角色的 LLM 实例。"""
        if role in self._clients:
            return self._clients[role]

        cfg = self._role_config(role)
        model = self.resolve_model(role)

        providers = self._data.get("provider_defaults", {}) or {}
        provider = providers.get(str(cfg.get("provider", "dashscope") or "dashscope"), {}) or {}
        base_url = str(cfg.get("base_url") or provider.get("base_url") or _DEFAULT_BASE_URL).strip()
        key_env = str(cfg.get("api_key_env") or provider.get("api_key_env") or _DEFAULT_API_KEY_ENV).strip()
        api_key = os.getenv(key_env, "").strip()
        if not api_key:
            raise ValueError(f"模型角色 '{role}' 缺少 API 密钥: 环境变量 {key_env} 未设置")

        # 阶段5: 超时与重试(provider 级默认, role 级可覆盖)
        timeout = _first_number(cfg.get("request_timeout"), provider.get("request_timeout"), default=120)
        retries = _first_number(cfg.get("max_retries"), provider.get("max_retries"), default=3)

        llm = ChatOpenAI(
            model=model,
            base_url=base_url,
            api_key=api_key,
            extra_body={"enable_thinking": False},
            request_timeout=timeout,
            max_retries=int(retries),
            # 自定义 base_url(DashScope)下 langchain 不会自动开启流式用量返回,
            # 显式开启使 astream 的最后 chunk 携带 usage → 用量看板统计完整
            stream_usage=True,
            callbacks=[self._usage_handler] if self._usage_handler else None,
        )
        self._clients[role] = llm
        logger.info(
            f"🤖 [ModelRouter] 角色 {role} → {model} ({base_url}, timeout={timeout}s, retries={int(retries)})"
        )
        return llm

    def describe(self) -> Dict[str, str]:
        """各角色当前型号(供启动日志/健康展示)。"""
        return {role: self.resolve_model(role) for role in _DEFAULT_MODELS}

    def info(self) -> Dict[str, Dict]:
        """各角色完整运行配置(型号/超时/重试), 供 /model/info 展示。"""
        result = {}
        providers = self._data.get("provider_defaults", {}) or {}
        for role in _DEFAULT_MODELS:
            cfg = self._role_config(role)
            provider = providers.get(str(cfg.get("provider", "dashscope") or "dashscope"), {}) or {}
            result[role] = {
                "model": self.resolve_model(role),
                "request_timeout": _first_number(cfg.get("request_timeout"), provider.get("request_timeout"), default=120),
                "max_retries": int(_first_number(cfg.get("max_retries"), provider.get("max_retries"), default=3)),
            }
        return result

    def _role_config(self, role: str) -> Dict:
        cfg = (self._data.get("roles", {}) or {}).get(role)
        if isinstance(cfg, dict):
            return cfg
        if role not in _DEFAULT_MODELS:
            logger.warning("[ModelRouter] 未知角色 '%s', 回退 main 配置", role)
            cfg = (self._data.get("roles", {}) or {}).get("main")
            return cfg if isinstance(cfg, dict) else {}
        return {}


def _first_number(*values, default):
    """取第一个非空数值配置, 全部缺失返回 default。"""
    for value in values:
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return default
