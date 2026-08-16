"""阶段7 安全合规测试(纯逻辑, 无需真实 API)。

运行: pytest tests/test_security.py -v
"""
import sys

import pytest
from pydantic import ValidationError

sys.path.insert(0, ".")

from app.utils.security import mask_sensitive, RequestConcurrencyGuard
from app.utils.error_codes import build_error_event
from app.main import QueryRequest, _validate_kb_files
from fastapi import HTTPException


# ── 日志脱敏 ──

def test_mask_id_card():
    text = "患者身份证 110101199003074518 与 110101900307451 需脱敏"
    masked = mask_sensitive(text)
    assert "110101199003074518" not in masked
    assert "110101900307451" not in masked
    assert masked.count("身份证号[已脱敏]") == 2


def test_mask_phone_and_bank_card():
    text = "联系电话13812345678, 银行卡6222020200112233445"
    masked = mask_sensitive(text)
    assert "13812345678" not in masked
    assert "6222020200112233445" not in masked
    assert "手机号[已脱敏]" in masked
    assert "银行卡号[已脱敏]" in masked


def test_mask_preserves_medical_content():
    text = "NIHSS 16分, 血压185/100mmHg, 发病90分钟"
    assert mask_sensitive(text) == text


def test_mask_empty_and_none():
    assert mask_sensitive("") == ""
    assert mask_sensitive(None) is None


# ── 错误事件脱敏 ──

def test_error_event_redacts_internal_details():
    exc = RuntimeError("内部机密: /app/secret.py line 42, api_key=xxx")
    event = build_error_event(exc, talk_id="t1")
    assert "/app/secret.py" not in event["content"]
    assert "api_key=xxx" not in event["content"]
    assert "line 42" not in event["error"]["detail"]
    assert event["error"]["code"] == "E1099"
    assert event["type"] == "error"


# ── 并发闸 ──

def test_guard_per_user_limit():
    guard = RequestConcurrencyGuard(per_user_limit=2, global_limit=8)
    assert guard.try_acquire("u1") is True
    assert guard.try_acquire("u1") is True
    assert guard.try_acquire("u1") is False  # 单用户上限
    assert guard.active() == 2
    guard.release("u1")
    assert guard.try_acquire("u1") is True
    assert guard.active() == 2


def test_guard_global_limit():
    guard = RequestConcurrencyGuard(per_user_limit=5, global_limit=2)
    assert guard.try_acquire("u1") is True
    assert guard.try_acquire("u2") is True
    assert guard.try_acquire("u3") is False  # 全局上限
    guard.release("u1")
    assert guard.try_acquire("u3") is True


def test_guard_release_never_negative():
    guard = RequestConcurrencyGuard(per_user_limit=2, global_limit=8)
    guard.release("nobody")  # 多余释放安全
    assert guard.active() == 0


# ── 输入长度限制 ──

def test_query_request_rejects_oversize_question():
    with pytest.raises(ValidationError):
        QueryRequest(question="x" * 20001, token="t")


def test_query_request_accepts_normal_input():
    req = QueryRequest(question="正常问题", token="t")
    assert req.question == "正常问题"


def test_query_request_rejects_too_many_images():
    with pytest.raises(ValidationError):
        QueryRequest(question="q", token="t", images=["img"] * 6)


# ── KB 上传防护 ──

def test_kb_upload_file_count_and_size_caps():
    with pytest.raises(HTTPException) as e1:
        _validate_kb_files([{"name": "a.pdf", "base64": "x"} for _ in range(11)])
    assert e1.value.status_code == 413
    with pytest.raises(HTTPException) as e2:
        _validate_kb_files([{"name": "big.pdf", "base64": "A" * 28_000_001}])
    assert e2.value.status_code == 413
    # 合法文件通过
    _validate_kb_files([{"name": "ok.pdf", "base64": "QUJD"} for _ in range(3)])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
