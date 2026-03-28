import json
import re
from typing import Dict, Any, List
from iteration1_eval.llm import SimpleLLM


class PlanningRationalityMetric:
    name = "planning_rationality"

    def __init__(self, llm: SimpleLLM = SimpleLLM()):
        self.llm = llm

    # ---------- 工具序列 ----------
    def _extract_tools(self, steps: List[Dict]) -> List[str]:
        return [s.get("tool_call") for s in steps if s.get("tool_call")]

    # ---------- LCS ----------
    def _lcs(self, a: List[str], b: List[str]) -> int:
        n, m = len(a), len(b)
        dp = [[0] * (m + 1) for _ in range(n + 1)]
        for i in range(n):
            for j in range(m):
                if a[i] == b[j]:
                    dp[i + 1][j + 1] = dp[i][j] + 1
                else:
                    dp[i + 1][j + 1] = max(dp[i][j + 1], dp[i + 1][j])
        return dp[n][m]

    # ---------- Correctness ----------
    def _rule_correctness(self, sample: Dict[str, Any]) -> float:
        expected = self._extract_tools(sample.get("expected_steps", []))
        actual = self._extract_tools(sample.get("steps", []))
        if not actual or not expected:
            return 0.0
        return self._lcs(expected, actual) / len(expected)

    # ---------- Loop detection ----------
    def _detect_loop(self, seq: List[str], max_window: int = 5) -> bool:
        n = len(seq)
        for w in range(1, min(max_window, n // 2) + 1):
            for i in range(n - 2 * w + 1):
                if seq[i:i + w] == seq[i + w:i + 2 * w]:
                    return True
        return False

    # ---------- Efficiency ----------
    def _rule_efficiency(self, sample: Dict[str, Any]) -> float:
        seq = self._extract_tools(sample.get("steps", []))
        expected_len = len(sample.get("expected_steps", []))

        if not seq or expected_len == 0:
            return 0.0

        unique_ratio = len(set(seq)) / len(seq)
        loop_penalty = 0.7 if self._detect_loop(seq) else 1.0

        # 对称效率
        length_eff = min(len(seq), expected_len) / max(len(seq), expected_len)

        return max(0.0, min(1.0, unique_ratio * loop_penalty * length_eff))

    # ---------- Prompt ----------
    def _build_prompt(self, sample: Dict[str, Any]) -> str:
        return f"""
You are an expert evaluator of AI agent planning quality.

You MUST strictly follow the rubric below.

----------------------
Evaluation Principles
----------------------
- Compare the actual trajectory against the expected plan
- Penalize missing steps, wrong order, redundant steps
- Apply proportional scoring (DO NOT give 0 unless completely wrong)

----------------------
Scoring Rubric (0 ~ 1)
----------------------

Logical Correctness:
- 1.0 = perfect order and structure
- 0.7 ~ 0.9 = minor deviation
- 0.4 ~ 0.6 = noticeable issues
- 0.1 ~ 0.3 = major errors
- 0.0 = completely incorrect logic

Dataflow Consistency:
- 1.0 = all steps use correct dependencies
- 0.7 ~ 0.9 = minor issues
- 0.4 ~ 0.6 = partial inconsistency
- 0.0 ~ 0.3 = broken data flow

Efficiency:
- 1.0 = no redundancy, minimal steps
- 0.7 ~ 0.9 = slight redundancy
- 0.4 ~ 0.6 = noticeable inefficiency
- 0.0 ~ 0.3 = highly redundant or looping

Completeness:
- 1.0 = all required steps present
- 0.6 ~ 0.8 = minor missing steps
- 0.3 ~ 0.5 = important steps missing
- 0.0 ~ 0.2 = critical steps missing

----------------------
Task Data
----------------------

[Expected Plan]
{json.dumps(sample.get("expected_steps"), ensure_ascii=False, indent=2)}

[Actual Trajectory]
{json.dumps(sample.get("steps"), ensure_ascii=False, indent=2)}

----------------------
Output Format (STRICT JSON)
----------------------
{{
  "reasoning": "...",
  "scores": {{
    "logical_correctness": float (0~1),
    "dataflow_consistency": float (0~1),
    "efficiency": float (0~1),
    "completeness": float (0~1)
  }}
}}

Rules:
- All scores MUST be between 0 and 1
- Do NOT output values outside this range
"""

    # ---------- Parse ----------
    def _parse_llm(self, text: str) -> Dict[str, Any]:
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```[a-zA-Z]*", "", text)
            text = text.rstrip("```")

        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return {}

        try:
            return json.loads(match.group())
        except:
            return {}

    # ---------- Clamp ----------
    def _clamp(self, x: float) -> float:
        return max(0.0, min(1.0, x))

    # ---------- LLM eval ----------
    def _llm_eval(self, sample: Dict[str, Any]) -> Dict[str, Any]:
        prompt = self._build_prompt(sample)
        resp = self.llm.generate(prompt)[0]
        parsed = self._parse_llm(resp)

        scores = parsed.get("scores", {})

        return {
            "logical_correctness": self._clamp(float(scores.get("logical_correctness", 0))),
            "dataflow_consistency": self._clamp(float(scores.get("dataflow_consistency", 0))),
            "efficiency": self._clamp(float(scores.get("efficiency", 0))),
            "completeness": self._clamp(float(scores.get("completeness", 0))),
            "reasoning": parsed.get("reasoning", "")
        }

    # ---------- Final score ----------
    def _compute(self, sample: Dict[str, Any]) -> Dict[str, Any]:
        rc = self._rule_correctness(sample)
        reff = self._rule_efficiency(sample)
        llm = self._llm_eval(sample)

        final_score = (
            0.35 * rc +
            0.15 * reff +
            0.2 * llm["logical_correctness"] +
            0.1 * llm["dataflow_consistency"] +
            0.1 * llm["efficiency"] +
            0.1 * llm["completeness"]
        )

        return {
            "metric": "Planning Rationality (RAGAS-style)",
            "score": round(self._clamp(final_score), 4),
            "details": {
                "rule_correctness": rc,
                "rule_efficiency": reff,
                "llm_scores": llm
            }
        }

    def score(self, sample: Dict[str, Any], llm=None):
        return self._compute(sample)

def build_metric():
    return PlanningRationalityMetric()

# ---------- main ----------
if __name__ == "__main__":
    data = [
        {
            "task_id": "42966ceff3ff344b",
            "steps": [
                {"tool_call": "search_restaurants"},
                {"tool_call": "search_products"},
                {"tool_call": "place_order"}
            ],
            "expected_steps": [
                {"tool_call": "search_restaurants"},
                {"tool_call": "search_products"},
                {"tool_call": "place_order"},
                {"tool_call": "pay_order"}
            ]
        }
    ]

    evaluator = PlanningRationalityMetric()

    for sample in data:
        result = evaluator.score(sample)
        print("\n======================")
        print("Task ID:", sample["task_id"])
        print("Score:", result["score"])
        print(json.dumps(result["details"], ensure_ascii=False, indent=2))