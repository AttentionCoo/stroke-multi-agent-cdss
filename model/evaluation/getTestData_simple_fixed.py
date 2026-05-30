import os
import sys
import argparse
import logging
import json
import re
import time
import requests
from collections import Counter
from typing import List, Dict, Any
from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib as mpl

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from datasets import load_dataset

mpl.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial Unicode MS']
mpl.rcParams['axes.unicode_minus'] = False

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("MedicalEvaluatorSimple")

def safe_text(x):
    if x is None:
        return ""
    if isinstance(x, (list, dict)):
        try:
            return json.dumps(x, ensure_ascii=False)
        except Exception:
            return str(x)
    return str(x).strip()

# 改进方案3：扩展神经内科关键词
EXPANDED_NEURO_KEYWORDS = [
    "神经", "脑", "卒中", "中风", "脑梗", "脑出血", "脑血管",
    "头痛", "头晕", "眩晕", "昏迷", "意识", "帕金森", "癫痫", "瘫痪",
    "阿尔茨海默", "痴呆", "多发性硬化", "重症肌无力", "肌无力",
    "格林巴利", "吉兰巴雷", "震颤", "共济失调", "认知障碍", "记忆障碍",
    "失语", "脑膜炎", "脑炎", "胶质瘤", "脑膜瘤", "CT", "MRI", "DSA",
    "麻木", "无力", "抽搐", "晕厥", "偏瘫", "截瘫", "感觉障碍"
]

GT_FIELD_CANDIDATES = [
    "diagnosis", "final_diagnosis", "label", "answer", "answers", "gold_answer",
    "ground_truth", "groundtruth", "diagnoses", "diagnostic", "结论", "诊断", "病理诊断",
    "诊断结果", "最终诊断", "参考答案", "pathology", "pathologic", "QA_pairs"
]

def extract_ground_truth(case):
    gt_list = []
    matched_fields = []
    
    if "QA_pairs" in case and case["QA_pairs"]:
        for qa in case["QA_pairs"]:
            if isinstance(qa, dict) and "answer" in qa:
                answer_text = str(qa["answer"]).strip()
                if answer_text:
                    gt_list.append(answer_text)
        if gt_list:
            matched_fields.append("QA_pairs")
    
    for key in GT_FIELD_CANDIDATES:
        if key == "QA_pairs":
            continue
        if key in case:
            v = case.get(key)
            if v:
                if isinstance(v, list):
                    for it in v:
                        s = str(it).strip()
                        if s:
                            gt_list.append(s)
                else:
                    s = str(v).strip()
                    if s:
                        gt_list.append(s)
                matched_fields.append(key)
    
    for k in case.keys():
        if k in GT_FIELD_CANDIDATES:
            continue
        low = k.lower()
        if "诊断" in k or "diagnos" in low or "pathol" in low:
            v = case.get(k)
            if v:
                s = str(v).strip()
                if s and s not in gt_list:
                    gt_list.append(s)
                    matched_fields.append(k)
    
    gt_list = [g for i,g in enumerate(gt_list) if g and g not in gt_list[:i]]
    return gt_list, matched_fields

def build_question_from_case(case):
    title = safe_text(case.get("title", ""))
    description = safe_text(case.get("description", ""))
    extra_parts = []
    for k in ("history", "past_history", "clinical_history", "present_illness", "abstract"):
        if case.get(k):
            extra_parts.append(safe_text(case.get(k)))
    extra_text = "\n".join(extra_parts)
    question_text = f"""你是一名神经内科医生，请根据以下病历做出专业诊断并给出诊断依据。

【病历标题】
{title}

【病史与检查】
{description}
{extra_text}

请给出：
1) 主要诊断（列出诊断名称）
2) 诊断依据（要点式）
3) 如果有推荐的下一步检查或鉴别诊断，也请简要列出。
"""
    return question_text

# 简单的HTTP LLM客户端
class SimpleLLMClient:
    def __init__(self, api_key=None, base_url=None, model="qwen-plus"):
        self.api_key = api_key or os.getenv("DASHSCOPE_API_KEY") or os.getenv("QWEN-API-KEY")
        self.base_url = base_url or "https://dashscope.aliyuncs.com/compatible-mode/v1"
        self.model = model
        
        if not self.api_key:
            logger.warning("未找到API Key")
    
    def invoke(self, messages, max_tokens=3000, temperature=0.7) -> str:
        if not self.api_key:
            return "API Key未配置"
        
        try:
            url = f"{self.base_url}/chat/completions"
            payload = {
                "model": self.model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature
            }
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            response = requests.post(url, json=payload, headers=headers, timeout=120)
            response.raise_for_status()
            
            result = response.json()
            return result["choices"][0]["message"]["content"]
            
        except Exception as e:
            logger.error(f"LLM API调用失败: {e}")
            return f"API调用失败: {str(e)}"

# 医学评测LLM
class MedicalJudgeLLM:
    def __init__(self, api_key=None):
        self.llm = SimpleLLMClient(api_key, model="qwen-plus")
        if self.llm.api_key:
            logger.info("✅ 医学评测LLM初始化成功")
    
    def evaluate_medical_quality(self, question: str, answer: str, reference: str) -> Dict[str, Any]:
        if not self.llm.api_key:
            return {"score": 0.5, "reasoning": "评测LLM不可用"}
        
        messages = [
            {
                "role": "system",
                "content": "你是资深神经内科主任医师，拥有20年临床经验。"
            },
            {
                "role": "user", 
                "content": f"""请从以下维度评估医学回答质量（0-1分）：
1. 诊断准确性
2. 依据充分性  
3. 鉴别完整性
4. 治疗合理性
5. 风险意识
6. 表达规范性

【问题】{question[:500]}
【模型回答】{answer[:1000]}
【参考答案】{reference[:500]}

返回JSON格式：{{"diagnosis_accuracy":分数,"evidence_sufficiency":分数,"differential_completeness":分数,"treatment_rationality":分数,"risk_awareness":分数,"expression_standard":分数,"overall_score":平均分,"strengths":["优点"],"weaknesses":["缺点"]}}"""
            }
        ]
        
        try:
            response = self.llm.invoke(messages, max_tokens=3000, temperature=0)
            result = self._parse_evaluation(response)
            return result
        except Exception as e:
            logger.error(f"医学评测失败: {e}")
            return {"score": 0.5, "reasoning": f"评测失败: {str(e)}"}
    
    def _parse_evaluation(self, text: str) -> Dict[str, Any]:
        try:
            json_match = re.search(r'\{[\s\S]*\}', text)
            if json_match:
                return json.loads(json_match.group())
        except:
            pass
        
        return {"score": 0.5, "reasoning": "无法解析评测结果"}

def ensure_dir(path):
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)

def analyze_eval_samples(eval_samples, out_dir="analysis_plots"):
    ensure_dir(out_dir)
    n = len(eval_samples)
    analysis = {}
    analysis['n_samples'] = n

    gt_counts = sum(1 for s in eval_samples if s.get("ground_truth") and not (len(s["ground_truth"]) == 1 and s["ground_truth"][0] == "AUTO_GROUND_TRUTH"))
    auto_gt_counts = sum(1 for s in eval_samples if s.get("ground_truth") and len(s["ground_truth"]) == 1 and s["ground_truth"][0] == "AUTO_GROUND_TRUTH")
    
    analysis['gt_found_count'] = gt_counts
    analysis['auto_gt_count'] = auto_gt_counts
    analysis['gt_found_rate'] = gt_counts / n if n else 0
    analysis['auto_gt_rate'] = auto_gt_counts / n if n else 0

    answer_lens = [len(safe_text(s.get("answer", ""))) for s in eval_samples]
    gt_lens = [len(" ".join(s.get("ground_truth", []))) for s in eval_samples]
    
    import statistics
    analysis['answer_len_stats'] = {
        "count": len(answer_lens),
        "mean": statistics.mean(answer_lens) if answer_lens else 0,
        "median": statistics.median(answer_lens) if answer_lens else 0,
        "min": min(answer_lens) if answer_lens else 0,
        "max": max(answer_lens) if answer_lens else 0
    }
    analysis['gt_len_stats'] = {
        "count": len(gt_lens),
        "mean": statistics.mean(gt_lens) if gt_lens else 0,
        "median": statistics.median(gt_lens) if gt_lens else 0,
        "min": min(gt_lens) if gt_lens else 0,
        "max": max(gt_lens) if gt_lens else 0
    }

    if answer_lens:
        plt.figure()
        plt.hist(answer_lens, bins='auto')
        plt.title("Agent回答长度分布")
        plt.xlabel("长度(字符)")
        plt.ylabel("数量")
        plt.savefig(os.path.join(out_dir, "answer_length_hist.png"))
        plt.close()

    return analysis

def generate_analysis_report(analysis: Dict[str, Any], medical_eval_results=None):
    md_lines = ["# 医学评测分析报告（简化版）\n"]
    md_lines.append(f"## 基本信息\n")
    md_lines.append(f"- 样本数: **{analysis.get('n_samples',0)}**\n")
    
    if medical_eval_results:
        overall_scores = [r.get("overall_score", 0) for r in medical_eval_results if "overall_score" in r]
        if overall_scores:
            avg_overall = sum(overall_scores) / len(overall_scores)
            md_lines.append(f"- 平均总体得分: **{avg_overall:.4f}**\n")
            
            if avg_overall >= 0.8:
                level = "🟢 优秀"
            elif avg_overall >= 0.6:
                level = "🟡 良好"
            elif avg_overall >= 0.4:
                level = "🟠 需改进"
            else:
                level = "🔴 需严重改进"
            md_lines.append(f"- 总体评估: {level}\n")
    
    with open("analysis_report.md", "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))
    logger.info("已保存 analysis_report.md")

def main_eval(test_count=10, keywords=None, dataset_name="FreedomIntelligence/CMB", subset="CMB-Clin",
              allow_no_gt=False, use_medical_judge=True):
    logger.info("=" * 60)
    logger.info("开始医学评测流程（简化版）")
    logger.info("=" * 60)
    
    llm_client = SimpleLLMClient(model="qwen-plus")
    medical_judge = MedicalJudgeLLM() if use_medical_judge else None
    
    logger.info("加载数据集: %s / %s", dataset_name, subset)
    try:
        raw_ds = load_dataset(dataset_name, subset, split="test")
        logger.info("数据集样本数 = %d", len(raw_ds))
    except Exception as e:
        logger.error(f"❌ 加载数据集失败: {e}")
        return

    if keywords is None or len(keywords) == 0:
        keywords = EXPANDED_NEURO_KEYWORDS
        logger.info(f"使用扩展神经内科关键词（共{len(keywords)}个）")

    eval_samples = []
    skipped_debug = []
    processed = 0
    neuro_cases_found = 0

    logger.info("开始筛选和处理样本...")
    for idx, case in enumerate(raw_ds):
        if processed >= test_count:
            break

        title = safe_text(case.get("title", ""))
        description = safe_text(case.get("description", ""))
        blob = (title + " " + description).strip()
        
        if not any(k in blob for k in keywords):
            skipped_debug.append({"dataset_idx": idx, "reason": "keyword_filter"})
            continue
        
        neuro_cases_found += 1
        
        question_text = build_question_from_case(case)
        ground_truth, matched_fields = extract_ground_truth(case)
        
        if not ground_truth:
            if allow_no_gt:
                ground_truth = ["AUTO_GROUND_TRUTH"]
            else:
                skipped_debug.append({"dataset_idx": idx, "reason": "no_ground_truth"})
                continue

        eval_samples.append({
            "question": question_text,
            "ground_truth": ground_truth,
            "gt_extracted_from_fields": matched_fields
        })
        processed += 1

    logger.info(f"筛选完成：找到{neuro_cases_found}个神经内科病例，准备评测{len(eval_samples)}个样本")
    
    if not eval_samples:
        logger.error("❌ 未提取到有效测试数据")
        return

    logger.info("开始生成回答...")
    eval_results = []
    start_time = time.time()
    
    for i, sample in enumerate(eval_samples):
        logger.info(f"处理样本 {i+1}/{len(eval_samples)}")
        
        messages = [
            {"role": "system", "content": "你是一名专业的神经内科医生，擅长根据病历信息做出准确诊断。"},
            {"role": "user", "content": sample['question']}
        ]
        
        answer = llm_client.invoke(messages, max_tokens=3000, temperature=0.7)
        
        eval_results.append({
            "question": sample['question'],
            "answer": answer,
            "contexts": [],  # 简化版不使用检索
            "ground_truth": sample['ground_truth'],
            "gt_extracted_from_fields": sample['gt_extracted_from_fields']
        })
    
    elapsed_time = time.time() - start_time
    logger.info(f"✅ 回答生成完成，耗时 {elapsed_time:.2f} 秒")

    pd.DataFrame(eval_results).to_csv("medical_agent_eval_details.csv", index=False, encoding="utf-8-sig")
    logger.info("已保存评测详情")

    medical_eval_results = []
    if medical_judge:
        logger.info("开始医学专业评测...")
        
        for i, sample in enumerate(eval_results):
            logger.info(f"医学评测样本 {i+1}/{len(eval_results)}")
            
            try:
                med_result = medical_judge.evaluate_medical_quality(
                    question=sample['question'],
                    answer=sample['answer'],
                    reference=" ".join(sample['ground_truth']) if isinstance(sample['ground_truth'], list) else sample['ground_truth']
                )
                medical_eval_results.append(med_result)
            except Exception as e:
                logger.error(f"医学评测失败: {e}")
                medical_eval_results.append({"error": str(e)})
        
        with open("medical_eval_results.json", "w", encoding="utf-8") as f:
            json.dump(medical_eval_results, f, ensure_ascii=False, indent=2)
        logger.info("已保存医学评测结果")

    logger.info("开始数据分析...")
    try:
        analysis = analyze_eval_samples(eval_results)
        with open("analysis_summary.json", "w", encoding="utf-8") as f:
            json.dump(analysis, f, ensure_ascii=False, indent=2)
        logger.info("已保存分析摘要")
        
        generate_analysis_report(analysis, medical_eval_results)
        
    except Exception as e:
        logger.error(f"❌ 数据分析失败: {e}")

    logger.info("=" * 60)
    logger.info("全部流程结束")
    logger.info("=" * 60)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="医学评测分析工具（简化版）")
    parser.add_argument("--test_count", type=int, default=10, help="评测样本数")
    parser.add_argument("--use_medical_judge", type=lambda s: s.lower() in ("true", "1", "yes"), default=True)
    parser.add_argument("--dataset_name", type=str, default="FreedomIntelligence/CMB")
    parser.add_argument("--subset", type=str, default="CMB-Clin")
    
    args = parser.parse_args()
    
    try:
        main_eval(
            test_count=args.test_count,
            use_medical_judge=args.use_medical_judge,
            dataset_name=args.dataset_name,
            subset=args.subset
        )
    except KeyboardInterrupt:
        logger.info("\n⚠️ 用户中断评测")
    except Exception as e:
        logger.error(f"❌ 评测过程出错: {e}")
        import traceback
        logger.error(traceback.format_exc())