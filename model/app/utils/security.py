"""阶段7 安全合规工具(HIPAA Safe Harbor 18 类 PHI 脱敏 + 请求并发闸)。

- mask_sensitive: 日志脱敏, 覆盖 HIPAA Safe Harbor 18 类中可在中文文本可靠识别的类别;
- detect_phi: 检测文本是否含 PHI(供合规审计节点使用);
- RequestConcurrencyGuard: 内存级请求并发闸(单用户 + 全局上限), 防滥用拖垮模型服务。

覆盖说明(对应 Safe Harbor 类别):
  [1] 姓名            → 中文姓名无法可靠正则识别, 不自动脱敏(依赖上游规范化)
  [2] 地理信息        → 邮编(6位, 带"邮编"前缀)
  [3] 日期(除年份)    → 完整日期(2024-05-12 / 2024年5月12日 / 5月12日)
  [3] 年龄 > 89       → 90-99 岁
  [4][5] 电话/传真    → 手机号 11 位; 座机/传真 010-XXXXXXXX
  [6] 电子邮箱        → 邮箱
  [7] 社保号/身份证   → 18/15 位身份证
  [8] 病历号          → 病案号/病历号/住院号/门诊号 后的编号
  [9][10] 保险/银行账号 → 银行卡 16-19 位; 医保/社保卡号
  [11] 证书/执照号    → 驾驶证/护照号(带前缀)
  [12] 车辆标识(车牌) → 中国车牌(省简+字母+5位)
  [14] URL            → http(s):// 与 www.
  [15] IP 地址        → IPv4
  [16] 生物标识       → 文本无法识别(依赖影像侧)
  [17] 全脸影像       → 非文本类
  [18] 其他唯一标识   → 设备序列号(带前缀, 如 SN:) 示例级支持

所有模式使用数字/字符 lookaround 而非 \b: Python re 的 \w 含中文,
中文字符旁 \b 不成立。
"""

import re
from typing import Dict, List

# 18 位身份证(含末位 X)、15 位旧身份证、11 位手机号、16-19 位银行卡
_ID_CARD_18 = re.compile(r"(?<!\d)\d{6}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx](?!\d)")
_ID_CARD_15 = re.compile(r"(?<!\d)\d{6}\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}(?!\d)")
_PHONE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
_BANK_CARD = re.compile(r"(?<!\d)\d{16,19}(?!\d)")

# ── HIPAA 扩展类别 ──────────────────────────────────────────
# 座机/传真(区号-号码)
_LANDLINE = re.compile(r"(?<!\d)0\d{2,3}[- ]?\d{7,8}(?!\d)")
# 邮箱
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# IPv4
_IPV4 = re.compile(r"(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?!\d)")
# URL
_URL = re.compile(r"https?://[^\s，。；、（）()\"']+|www\.[^\s，。；、（）()\"']+")
# 车牌(省份简+发牌机关字母+5位)
_PLATE = re.compile(r"[京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤青藏川宁琼使领][A-Z][A-Z0-9]{5}")
# 精确日期(含年月日或月日): 2024-05-12 / 2024年5月12日 / 5月12日
_FULL_DATE = re.compile(r"(?<!\d)\d{4}[-/年.]\d{1,2}[-/月.]\d{1,2}日?|(?<!\d)\d{1,2}月\d{1,2}日")
# 年龄 > 89(90-99 岁)
_AGE_OVER_89 = re.compile(r"(?<!\d)9\d岁(?!\d)")
# 病历号/住院号/门诊号
_MEDICAL_RECORD = re.compile(r"(病案号|病历号|住院号|门诊号)\s*[:：]?\s*[A-Za-z0-9-]{4,20}")
# 医保/社保卡号
_INSURANCE_ID = re.compile(r"(医保卡号|社保卡号|社会保障号|医保号|SSN)\s*[:：]?\s*[\dX-]{6,}")
# 驾照/护照号
_LICENSE_NO = re.compile(r"(驾驶证号|驾照号|护照号)\s*[:：]?\s*[A-Za-z0-9-]{6,12}")
# 设备序列号(SN:/序列号:)
_SERIAL_NO = re.compile(r"(SN|序列号)\s*[:：]?\s*[A-Za-z0-9-]{6,20}")

# 脱敏规则顺序: 先具体后宽泛(身份证必须先于日期, 避免 18 位数字被拆段)
_MASKS = [
    ("身份证号[已脱敏]", _ID_CARD_18),
    ("身份证号[已脱敏]", _ID_CARD_15),
    ("手机号[已脱敏]", _PHONE),
    ("银行卡号[已脱敏]", _BANK_CARD),
    ("座机号[已脱敏]", _LANDLINE),
    ("邮箱[已脱敏]", _EMAIL),
    ("IP地址[已脱敏]", _IPV4),
    ("网址[已脱敏]", _URL),
    ("车牌号[已脱敏]", _PLATE),
    ("日期[已脱敏]", _FULL_DATE),
    ("年龄[已脱敏]", _AGE_OVER_89),
    ("病历号[已脱敏]", _MEDICAL_RECORD),
    ("医保号[已脱敏]", _INSURANCE_ID),
    ("证件号[已脱敏]", _LICENSE_NO),
    ("序列号[已脱敏]", _SERIAL_NO),
]

# PHI 类别名(供合规审计节点结构化输出)
_PHI_LABELS = [
    ("身份证", _ID_CARD_18),
    ("身份证", _ID_CARD_15),
    ("手机号", _PHONE),
    ("银行卡", _BANK_CARD),
    ("座机号", _LANDLINE),
    ("邮箱", _EMAIL),
    ("IP地址", _IPV4),
    ("网址", _URL),
    ("车牌号", _PLATE),
    ("日期", _FULL_DATE),
    ("年龄>89", _AGE_OVER_89),
    ("病历号", _MEDICAL_RECORD),
    ("医保号", _INSURANCE_ID),
    ("证件号", _LICENSE_NO),
    ("序列号", _SERIAL_NO),
]


def mask_sensitive(text: str) -> str:
    """把常见个人敏感信息替换为掩码, 供日志输出前调用。"""
    if not text:
        return text
    masked = text
    for replacement, pattern in _MASKS:
        masked = pattern.sub(replacement, masked)
    return masked


def detect_phi(text: str) -> List[str]:
    """检测文本中出现的 PHI 类别(供合规审计节点使用)。

    返回命中的类别名列表(去重、保序); 文本为空返回空列表。
    """
    if not text:
        return []
    found: List[str] = []
    for label, pattern in _PHI_LABELS:
        if pattern.search(text) and label not in found:
            found.append(label)
    return found


class RequestConcurrencyGuard:
    """单事件循环内的并发计数器(无 await 的检查-递增是原子的, 无需锁)。"""

    def __init__(self, per_user_limit: int = 2, global_limit: int = 8):
        self.per_user_limit = max(1, int(per_user_limit))
        self.global_limit = max(1, int(global_limit))
        self._counts: Dict[str, int] = {}
        self._total = 0

    def try_acquire(self, key: str) -> bool:
        """尝试占用一个并发名额, 成功返回 True(必须配 release)。"""
        if self._total >= self.global_limit:
            return False
        if self._counts.get(key, 0) >= self.per_user_limit:
            return False
        self._total += 1
        self._counts[key] = self._counts.get(key, 0) + 1
        return True

    def release(self, key: str):
        """释放一个并发名额(与 try_acquire 成功一一对应)。"""
        if self._counts.get(key, 0) <= 1:
            self._counts.pop(key, None)
        else:
            self._counts[key] -= 1
        self._total = max(0, self._total - 1)

    def active(self) -> int:
        """当前在途请求数(供 /model/info 展示)。"""
        return self._total
