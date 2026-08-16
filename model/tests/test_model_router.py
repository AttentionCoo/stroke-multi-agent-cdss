"""阶段4 多模型解耦测试(ModelRouter, mock 环境变量, 无需真实 API)。

运行: pytest tests/test_model_router.py -v
"""
import sys
import os

import pytest

sys.path.insert(0, ".")

from app.config.model_router import ModelRouter


@pytest.fixture
def clean_env(monkeypatch):
    """清空所有模型相关环境变量, 保证测试隔离。"""
    for name in ("MODEL_MAIN", "MODEL_FAST", "MODEL_TURBO", "MODEL_CONSENSUS", "CONSENSUS_MODEL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    return monkeypatch


def test_default_models(clean_env):
    router = ModelRouter()
    assert router.resolve_model("main") == "qwen-plus"
    assert router.resolve_model("fast") == "qwen-plus"
    assert router.resolve_model("turbo") == "qwen-turbo"
    assert router.resolve_model("consensus") == "qwen-plus"


def test_env_override_per_role(clean_env):
    clean_env.setenv("MODEL_MAIN", "qwen-max")
    clean_env.setenv("MODEL_TURBO", "qwen-plus")
    router = ModelRouter()
    assert router.resolve_model("main") == "qwen-max"
    assert router.resolve_model("turbo") == "qwen-plus"
    # 未覆盖的角色保持默认
    assert router.resolve_model("fast") == "qwen-plus"


def test_legacy_consensus_env_compat(clean_env):
    """阶段3 之前的 CONSENSUS_MODEL 环境变量仍应生效(向后兼容)。"""
    clean_env.setenv("CONSENSUS_MODEL", "qwen-max")
    router = ModelRouter()
    assert router.resolve_model("consensus") == "qwen-max"


def test_model_consensus_preferred_over_legacy(clean_env):
    """同时设置 MODEL_CONSENSUS 与 CONSENSUS_MODEL 时, 新变量优先。"""
    clean_env.setenv("CONSENSUS_MODEL", "qwen-max")
    clean_env.setenv("MODEL_CONSENSUS", "qwen-plus")
    router = ModelRouter()
    assert router.resolve_model("consensus") == "qwen-plus"


def test_get_llm_creates_and_caches(clean_env):
    router = ModelRouter()
    llm1 = router.get_llm("main")
    llm2 = router.get_llm("main")
    assert llm1 is llm2
    # 不同角色不共用实例(共识角色独立, 便于单独升级型号)
    turbo = router.get_llm("turbo")
    assert turbo is not llm1
    assert turbo.model_name == "qwen-turbo"


def test_get_llm_env_override_applied(clean_env):
    clean_env.setenv("MODEL_MAIN", "qwen-max")
    router = ModelRouter()
    llm = router.get_llm("main")
    assert llm.model_name == "qwen-max"


def test_unknown_role_falls_back_to_main(clean_env):
    router = ModelRouter()
    assert router.resolve_model("nonexistent") == "qwen-plus"


def test_describe_lists_all_roles(clean_env):
    router = ModelRouter()
    desc = router.describe()
    assert set(desc.keys()) == {"main", "fast", "turbo", "consensus"}
    assert desc["turbo"] == "qwen-turbo"


def test_get_llm_applies_timeout_and_retries(clean_env):
    """阶段5: provider 默认 request_timeout=120 / max_retries=3 应落到客户端。"""
    router = ModelRouter()
    llm = router.get_llm("main")
    assert llm.request_timeout == 120
    assert llm.max_retries == 3
    info = router.info()
    assert info["main"]["request_timeout"] == 120
    assert info["main"]["max_retries"] == 3


def test_role_level_timeout_override(tmp_path, clean_env):
    """role 级配置可覆盖 provider 默认超时。"""
    import yaml as _yaml
    cfg_path = tmp_path / "models.yaml"
    cfg_path.write_text(_yaml.safe_dump({
        "provider_defaults": {
            "dashscope": {"base_url": "https://x", "api_key_env": "DASHSCOPE_API_KEY",
                          "request_timeout": 120, "max_retries": 3},
        },
        "roles": {
            "main": {"model": "qwen-plus", "request_timeout": 30, "max_retries": 1},
            "fast": {"model": "qwen-plus"},
            "turbo": {"model": "qwen-turbo"},
            "consensus": {"model": "qwen-plus"},
        },
    }), encoding="utf-8")
    router = ModelRouter(config_file=str(cfg_path))
    llm = router.get_llm("main")
    assert llm.request_timeout == 30
    assert llm.max_retries == 1
    # 未覆盖角色保持 provider 默认
    assert router.get_llm("fast").request_timeout == 120


def test_info_reports_all_roles_config(clean_env):
    router = ModelRouter()
    info = router.info()
    assert set(info.keys()) == {"main", "fast", "turbo", "consensus"}
    for role in info:
        assert "model" in info[role]
        assert info[role]["request_timeout"] == 120
        assert info[role]["max_retries"] == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
