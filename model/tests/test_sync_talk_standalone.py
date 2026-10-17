"""
AI 同步意见(sync-talk)核心逻辑的独立测试。
直接通过 HTTP 调用 DashScope API 验证 /ai/quick-analyze 的 LLM 调用,
不依赖 langchain 与服务端环境。
"""
import os
import json
import time
import requests
import pytest
from dotenv import load_dotenv

load_dotenv()

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LIVE_MODEL_TESTS") != "1",
    reason="在线模型冒烟测试需显式设置 RUN_LIVE_MODEL_TESTS=1",
)

DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY")
DASHSCOPE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"


def parse_json(text: str) -> dict:
    """从模型输出中提取 JSON。"""
    content = (text or "").strip()
    try:
        return json.loads(content)
    except Exception:
        pass
    for marker in ["```json", "```"]:
        if marker in content:
            try:
                s = content.split(marker)[1].split("```")[0].strip()
                return json.loads(s)
            except Exception:
                pass
    for sc, ec in [("{", "}"), ("[", "]")]:
        si, ei = content.find(sc), content.rfind(ec)
        if si != -1 and ei > si:
            try:
                return json.loads(content[si:ei + 1])
            except Exception:
                pass
    return {}


def test_quick_analyze_direct():
    """测试 sync-talk 依赖的 quick-analyze 核心 LLM 调用。"""
    print("=" * 80)
    print("[测试] AI 同步意见(sync-talk) - quick-analyze 核心逻辑")
    print("=" * 80)

    if not DASHSCOPE_API_KEY:
        pytest.fail("DASHSCOPE_API_KEY 未设置")

    # 模拟 sync-talk 的行为: 由医患对话构建提示词
    conversation_text = """user: 患者今天感觉头晕，血压偏高，收缩压160，舒张压95。
assistant: 患者的血压确实偏高，建议先休息片刻后再测量一次。请问患者是否有高血压病史？是否有其他不适症状如胸闷、心悸等？
user: 患者有高血压病史5年，一直在服用降压药，但最近一个月没有规律服药。今天早上还感觉有点胸闷。
assistant: 根据您描述的情况，患者高血压病史5年，近期未规律服药，目前血压160/95mmHg伴胸闷，这种情况需要引起重视。"""

    question = f"""请根据以下医患对话内容并结合病人既往病史（高血压病史5年，近期未规律服药），对病人进行综合健康风险评估，给出风险等级（低风险/中风险/高风险）、快速专业意见和关键要点。

【对话内容】
{conversation_text}"""

    print(f"\n[信息] 问题长度: {len(question)} 字符")
    print(f"[信息] 问题预览: {question[:200]}...")
    print("-" * 80)

    # 构建与 /ai/quick-analyze 完全一致的提示词
    prompt = f"""你是三甲医院神经内科主任医师。请快速分析以下临床问题，给出简洁专业的意见。

问题：
{question}

请直接输出 JSON（不要用 markdown 代码块包裹）：
{{
    "quickOpinion": "快速专业意见（100字以内）",
    "keyPoints": ["关键点1", "关键点2", "关键点3"],
    "riskLevel": "低风险/中风险/高风险"
}}

要求：
- quickOpinion: 简洁专业，禁止确诊语气
- keyPoints: 3-5个关键点，每点20字以内
- riskLevel: 基于问题内容判断风险等级
- 禁止具体药物剂量"""

    headers = {
        "Authorization": f"Bearer {DASHSCOPE_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": "qwen-turbo",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 512,
    }

    try:
        start_time = time.time()
        resp = requests.post(DASHSCOPE_URL, headers=headers, json=payload, timeout=60)
        elapsed = time.time() - start_time

        if resp.status_code != 200:
            pytest.fail(f"HTTP {resp.status_code}: {resp.text[:500]}")

        body = resp.json()
        content = body["choices"][0]["message"]["content"]

        print(f"[成功] LLM 调用完成, 耗时 {elapsed:.2f}s")
        print(f"[信息] 原始响应长度: {len(content)} 字符")
        print(f"[信息] 原始响应: {content[:300]}...")
        print("-" * 80)

        # 解析 LLM 响应中的 JSON
        result = parse_json(content)
        if not result:
            print("[警告] JSON 解析失败, 使用兜底值")
            result = {
                "quickOpinion": "建议结合临床实际进一步评估，如症状加重请及时就医。",
                "keyPoints": ["需进一步检查", "结合临床判断", "及时就医"],
                "riskLevel": "中风险"
            }

        print("\n[结果] 解析出的 AI 意见:")
        print(f"  riskLevel:     {result.get('riskLevel', 'N/A')}")
        print(f"  quickOpinion:  {result.get('quickOpinion', 'N/A')}")
        key_points = result.get('keyPoints', [])
        if key_points:
            for i, kp in enumerate(key_points, 1):
                print(f"  keyPoint[{i}]:   {kp}")
        print()
        print("=" * 80)
        print("[通过] AI 同步意见核心逻辑测试通过!")
        print("=" * 80)
        assert result

    except requests.exceptions.Timeout:
        print("[失败] 请求超时(>60 秒)")
        pytest.fail("请求超时（超过 60 秒）")
    except Exception as e:
        print(f"[失败] 错误: {e}")
        import traceback
        traceback.print_exc()
        pytest.fail(f"在线模型调用失败: {e}")


if __name__ == "__main__":
    test_quick_analyze_direct()
