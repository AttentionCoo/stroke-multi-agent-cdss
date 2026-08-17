"""阶段7 安全合规测试(纯逻辑, 无需真实 API)。

运行: pytest tests/test_security.py -v
"""
import sys

import pytest
from pydantic import ValidationError

sys.path.insert(0, ".")

from app.utils.security import mask_sensitive, detect_phi, RequestConcurrencyGuard
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
    text = "NIHSS 16分, 血压185/100mmHg, 发病90分钟, 发病时间3小时"
    assert mask_sensitive(text) == text


def test_mask_empty_and_none():
    assert mask_sensitive("") == ""
    assert mask_sensitive(None) is None


# ── HIPAA 18 类扩展类别 ──

def test_mask_email_ip_url():
    text = "邮箱 a.b_c@example.com, IP 192.168.1.10, 网址 https://hosp.cn/x?a=1 或 www.hosp.cn"
    masked = mask_sensitive(text)
    assert "a.b_c@example.com" not in masked
    assert "192.168.1.10" not in masked
    assert "hosp.cn" not in masked
    assert "邮箱[已脱敏]" in masked
    assert "IP地址[已脱敏]" in masked
    assert "网址[已脱敏]" in masked


def test_mask_full_date_and_age_over_89():
    text = "出生日期2024年5月12日, 入院5月12日, 年龄93岁, 血压2024/5/12, 统计年份2024年"
    masked = mask_sensitive(text)
    assert "2024年5月12日" not in masked
    assert "5月12日" not in masked
    assert "93岁" not in masked
    assert "2024/5/12" not in masked
    # 年份单独保留(HIPAA 允许保留年份)
    assert "2024年" in masked


def test_mask_plate_and_medical_record():
    text = "车牌京A12345, 病历号:ZY2026-0001, 医保卡号 100123456789"
    masked = mask_sensitive(text)
    assert "京A12345" not in masked
    assert "ZY2026-0001" not in masked
    assert "100123456789" not in masked
    assert "车牌号[已脱敏]" in masked
    assert "病历号[已脱敏]" in masked
    assert "医保号[已脱敏]" in masked


def test_mask_landline_license_serial():
    text = "电话010-88886666, 驾驶证号BJ123456789, SN:ABC-XYZ-2024"
    masked = mask_sensitive(text)
    assert "010-88886666" not in masked
    assert "座机号[已脱敏]" in masked
    assert "证件号[已脱敏]" in masked
    assert "序列号[已脱敏]" in masked


def test_detect_phi_labels():
    text = "联系电话13812345678, 身份证110101199003074518, 邮箱x@y.com"
    labels = detect_phi(text)
    assert "手机号" in labels
    assert "身份证" in labels
    assert "邮箱" in labels
    # 纯医学文本无 PHI
    assert detect_phi("NIHSS 16分, 发病90分钟, 时间窗内, 溶栓") == []



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
