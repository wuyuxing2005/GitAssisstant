from openai import OpenAI
from dataclasses import dataclass
from typing import List, Dict, Any
import json
import re
from iteration1_eval.llm import SimpleLLM

def extract_json_from_text(text: str) -> dict:
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        return {}

class ToolCallF1Metric:
    name = "tool_call_f1"

    def __init__(self, llm: SimpleLLM = SimpleLLM()):
        self.llm = llm

    def _evaluate_tool_calls(self, sample: Dict[str, Any]) -> dict:
        expected_steps = sample.get("expected_steps", [])
        actual_steps = sample.get("steps", [])

        if not expected_steps and not actual_steps:
            return {"matches": [], "unmatched_expected": [], "unmatched_actual": []}

        expected_formatted = []
        for i, s in enumerate(expected_steps):
            expected_formatted.append({
                "id": f"E{i}",
                "tool_call": s.get("tool_call"),
                "input": s.get("input")
            })

        actual_formatted = []
        for i, s in enumerate(actual_steps):
            actual_formatted.append({
                "id": f"A{i}",
                "tool_call": s.get("tool_call"),
                "input": s.get("input")
            })

        prompt = f"""
        You are an expert evaluator assessing the performance of an AI Agent.
        I will provide you with a list of "Expected Tool Calls" and a list of "Actual Tool Calls" made by the agent.
        Your task is to match each Expected Tool Call to an Actual Tool Call.

        A match is considered valid if:
        1. The `tool_call` names match exactly.
        2. The `input` arguments are semantically equivalent for achieving the goal, even if they differ slightly in syntax or phrasing.

        Expected Tool Calls:
        {json.dumps(expected_formatted, ensure_ascii=False, indent=2)}

        Actual Tool Calls:
        {json.dumps(actual_formatted, ensure_ascii=False, indent=2)}

        Respond ONLY in the following valid JSON format:
        {{
            "matches": [
                {{"expected_id": "E...", "actual_id": "A...", "reason": "brief reason here"}}
            ],
            "unmatched_expected": ["E..."],
            "unmatched_actual": ["A..."]
        }}
        Ensure the JSON is perfectly valid and nothing else is in your output.
        """
        
        resp_text = self.llm.generate(prompt)[0]
        parsed_data = self._parse_json_result(resp_text)
        return parsed_data

    def _parse_json_result(self, text: str) -> dict:
        text = text.strip()
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]

        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            text = match.group()

        try:
            return json.loads(text.strip())
        except json.JSONDecodeError as e:
            print(f"JSON 解析失败! 错误信息: {e}")
            return {"matches": [], "unmatched_expected": [], "unmatched_actual": []}

    def _compute(self, sample: Dict[str, Any]) -> Dict[str, Any]:
        expected_steps = sample.get("expected_steps", [])
        actual_steps = sample.get("steps", [])

        if not expected_steps and not actual_steps:
            return {"score": 1.0, "details": "No tool calls expected or made. Perfect score."}
            
        if not expected_steps:
            # 所有的实际调用都是多余的 (False Positives)
            return {"score": 0.0, "details": f"0 expected, {len(actual_steps)} actual"}
            
        if not actual_steps:
            # 期望调用但实际未调用 (False Negatives)
            return {"score": 0.0, "details": f"{len(expected_steps)} expected, 0 actual"}

        eval_result = self._evaluate_tool_calls(sample)

        matches = eval_result.get("matches", [])
        unmatched_expected = eval_result.get("unmatched_expected", [])
        unmatched_actual = eval_result.get("unmatched_actual", [])
        
        expected_count = len(expected_steps)
        actual_count = len(actual_steps)

        # 严格基于 ID 匹配计算 TP (真实匹配数), 过滤重复匹配以防大模型产生幻觉输出多个无意义的 match
        valid_matches = set()
        for m in matches:
            eid = m.get("expected_id")
            aid = m.get("actual_id")
            if eid and aid:
                valid_matches.add((eid, aid))

        # 确保 tp 数量不会超过预期的最大列表长度
        tp = min(len(valid_matches), expected_count, actual_count)
        
        # 计算假阳性(FP): 实际调用减去匹配上的数量 (也等价于未匹配上的实际调用量)
        # 计算假阴性(FN): 期望调用减去匹配上的数量 (也等价于未匹配上的期望调用量)
        fp = actual_count - tp
        fn = expected_count - tp
        
        precision = tp / actual_count if actual_count > 0 else 0.0
        recall = tp / expected_count if expected_count > 0 else 0.0
        
        f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

        return {
            "metric": self.name,
            "score": round(f1, 4),
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "true_positives": tp,
            "false_positives": fp,
            "false_negatives": fn,
            "reasoning": eval_result
        }

    def score(self, sample: Dict[str, Any], llm=None):
        if llm is not None:
            self.llm = llm
        result = self._compute(sample)
        # 返回完整的字典结果，evaluator 可以通过 result.get("tool_call_f1")["score"] 提取最终分数
        return result

def build_metric():
    return ToolCallF1Metric()
