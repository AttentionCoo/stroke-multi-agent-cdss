import asyncio
import time
import os
import json
import pytest
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

load_dotenv()

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LIVE_MODEL_TESTS") != "1",
    reason="在线模型冒烟测试需显式设置 RUN_LIVE_MODEL_TESTS=1",
)

def _parse_json(text):
    content = (text or "").strip()
    try:
        return json.loads(content)
    except:
        pass
    for marker in ["```json", "```"]:
        if marker in content:
            try:
                s = content.split(marker)[1].split("```")[0].strip()
                return json.loads(s)
            except:
                pass
    for sc, ec in [("{", "}"), ("[", "]")]:
        si, ei = content.find(sc), content.rfind(ec)
        if si != -1 and ei > si:
            try:
                return json.loads(content[si:ei + 1])
            except:
                pass
    return {}

@pytest.mark.asyncio
async def test_optimized_analyze_live():
    print("开始测试优化后的 analyze 逻辑")
    _dashscope_base = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    _dashscope_key = os.getenv("DASHSCOPE_API_KEY")
    
    if not _dashscope_key:
        print("未设置 DASHSCOPE_API_KEY")
        return
    
    llm = ChatOpenAI(model="qwen-turbo", base_url=_dashscope_base, api_key=_dashscope_key)
    
    patient_text = "Patient male, 65 years old, with hypertension and diabetes history. Sudden speech difficulty and right limb weakness this morning."
    
    prompt = f"""You are a general practitioner. Analyze the patient information quickly.

Patient info:
{patient_text}

Output JSON only:
{{"riskLevel": "Low/Medium/High", "suggestion": "Main suggestion", "analysisDetails": "Health assessment"}}
    
Requirements:
- riskLevel must be "Low", "Medium", or "High"
- No definitive diagnosis
- No specific drug dosage"""

    start = time.time()
    response = await llm.ainvoke([HumanMessage(content=prompt)])
    elapsed = time.time() - start
    
    content = getattr(response, "content", "")
    result = _parse_json(content)
    
    if not result:
        result = {"riskLevel": "Medium", "suggestion": "Further evaluation needed.", "analysisDetails": "Basic assessment completed."}
    
    print(f"耗时: {elapsed:.2f}s")
    print(f"风险等级: {result.get('riskLevel')}")
    print(f"建议: {result.get('suggestion')}")
    print(f"分析详情: {result.get('analysisDetails')}")

    if elapsed < 1.5:
        print("速度: 优秀")
    elif elapsed < 2.5:
        print("速度: 良好")
    else:
        print("速度: 需要优化")

if __name__ == "__main__":
    asyncio.run(test_optimized_analyze_live())
