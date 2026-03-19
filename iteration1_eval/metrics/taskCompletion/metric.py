from openai import OpenAI
from dataclasses import dataclass
from typing import List, Dict, Any
import json
import re
from iteration1_eval.llm import SimpleLLM
def extract_json_from_text(text: str) -> dict:
    """JSON 提取器"""
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

class TaskCompletionMetric:
    name="task_completion"
    def __init__(self, llm: SimpleLLM=SimpleLLM()):
        self.llm = llm
        

    def _extract_require(self, sample: Dict[str, Any]) -> List[Dict[str, Any]]:
        """步骤 1: 拆解原子需求与权重"""
        context = {
            "user_query": sample.get("user_query"),
            "ground_truth": sample.get("ground_truth"),
            "expected_steps": sample.get("expected_steps")
        }
        
        prompt = f"""
        You are an expert in requirement analysis.
        Please analyze the following JSON data (which contains user_query, ground_truth, and expected_steps).
        Break down the user's intent and expected actions into atomic requirements (single, independent demands).
        Assign a weight (a float between 0.0 and 1.0) to each requirement based on its importance to the overall task.
        The sum of all weights must be exactly 1.0!
        Input Context:
        {json.dumps(context, ensure_ascii=False, indent=2)}

        Strictly output a JSON object containing a "requirements" list, like this:
        {{
            "requirements":[
                {{"requirement": "查询张记烤肉店的restaurant_id", "weight": 0.2}},
                {{"requirement": "查询双人套餐的信息和库存", "weight": 0.8}}
            ]
        }}
        """
        resp_text = self.llm.generate(prompt)[0]
        parsed_data = self._parse_requirement_weight(resp_text)
        return parsed_data

    def _parse_requirement_weight(self,resp: str) -> list:
        """
        将 LLM 的文本输出解析为包含 {需求名, 权重} 的列表
        """
        resp = resp.strip()
        if resp.startswith("```json"):
            resp = resp[7:]
        elif resp.startswith("```"):
            resp = resp[3:]
        if resp.endswith("```"):
            resp = resp[:-3]
        match = re.search(r'\{.*\}', resp, re.DOTALL)
        if match:
            json_str = match.group()
            # data = json.loads(json_str)
            resp=json_str
            # print(data)
        else:
            print("没有找到 JSON")
        resp = resp.strip()

        try:
            # 解析 JSON
            parsed_data = json.loads(resp)
            
            # 格式化提取 {需求名, 权重}，并做容错验证
            if isinstance(parsed_data, dict):
                parsed_data = parsed_data.get("requirements", [])

            result_list = []
            if isinstance(parsed_data, list):
                for item in parsed_data:
                    req_name = item.get("requirement") or item.get("name") or item.get("需求名")
                    weight = item.get("weight") or item.get("权重")
                    
                    if req_name and weight is not None:
                        result_list.append({
                            "requirement": str(req_name).strip(),
                            "weight": float(weight)
                        })

            return result_list

        except json.JSONDecodeError as e:
            print(f"JSON 解析失败! 错误信息: {e}")
            print(f"LLM 原始输出: {resp}")
            
            # 备用方案  如果 LLM 没按 JSON 输出，尝试正则兜底提取
            # 匹配类似于 "1. 需求名: 0.3" 或 "- 需求名 (0.3)" 等常见格式
            fallback_list =[]
            lines = resp.split('\n')
            for line in lines:
                # 匹配包含数字（权重）的行，简单提取
                match = re.search(r'(.*?)(?:[:\-（(]?\s*(0\.\d+|1\.0|\d+%)\s*[)）]?)', line)
                if match:
                    name = match.group(1).strip(' -*.0123456789')
                    weight_str = match.group(2)
                    if name and weight_str:
                        try:
                            weight = float(weight_str.replace('%', '')) / 100 if '%' in weight_str else float(weight_str)
                            fallback_list.append({"requirement": name, "weight": weight})
                        except:
                            pass
            return fallback_list
        
    def _verify_requirements(self, requirements: List[Dict], sample: Dict[str, Any]) -> List[Dict[str, Any]]:
        """步骤 2: 验证实际轨迹是否满足了需求"""
        actual_trajectory = {
            "steps": sample.get("steps"),
            "final_answer": sample.get("final_answer")
        }
        # print(requirements)
        req_list_str = json.dumps([r["requirement"] for r in requirements], ensure_ascii=False)
        
        prompt = f"""
        You are an evaluator. I will give you a list of "atomic requirements" and the "actual execution trajectory" of an AI Agent.
        Your task is to judge whether each requirement is FULLY MET by the Agent's execution.

        Atomic Requirements:
        {req_list_str}

        Agent's Actual Execution Trajectory:
        {json.dumps(actual_trajectory, ensure_ascii=False, indent=2)}

        Strictly output a JSON object containing a "results" list. For each requirement, output true or false, and briefly explain why.
        Format:
        {{
            "results":[
                {{
                    "requirement": "查询张记烤肉店的restaurant_id", 
                    "is_met": true, 
                    "reasoning": "Agent called search_restaurants and got R1001."
                }}
            ]
        }}
        """
        resp_text = self.llm.generate(prompt)[0]
        parsed_data = extract_json_from_text(resp_text)
        return parsed_data.get("results",[])

    def _compute(self, sample: Dict[str, Any]) -> Dict[str, Any]:
        """步骤 3: 综合计算得分"""
        # print(type(sample))
        # 拆解需求
        requirements = self._extract_require(sample)
        if not requirements:
            return {
                "metric": "Task Completion (Ragas-style Atomic Verification)",
                "score": 0.0,
                "satisfied_weight": 0.0,
                "total_weight": 0.0,
                "details": [],
                "reasoning": "Failed to extract requirements."
            }

        # 验证需求
        verifications = self._verify_requirements(requirements, sample)
        
        # 建立验证字典，方便根据需求名查找结果
        verify_dict = {v["requirement"]: v for v in verifications}

        total_weight = 0.0
        satisfied_weight = 0.0
        details =[]

        # 计算公式: 满足的权重之和 / 总权重
        for req in requirements:
            req_name = req["requirement"]
            weight = float(req.get("weight", 0.0))
            total_weight += weight
            
            # 判断是否被满足
            is_met = False
            reasoning = "Not evaluated"
            if req_name in verify_dict:
                is_met = verify_dict[req_name].get("is_met", False)
                reasoning = verify_dict[req_name].get("reasoning", "")
                
            if is_met:
                satisfied_weight += weight
                
            details.append({
                "requirement": req_name,
                "weight": weight,
                "is_met": is_met,
                "reasoning": reasoning
            })

        # 防御性计算，避免除以 0
        score = (satisfied_weight / total_weight) if total_weight > 0 else 0.0

        return {
            "metric": "Task Completion (Ragas-style Atomic Verification)",
            "score": round(score, 4),
            "satisfied_weight": round(satisfied_weight, 4),
            "total_weight": round(total_weight, 4),
            "details": details
        }
    
    def score(self, sample:Dict[str, Any],llm:SimpleLLM):
        if llm is not None:
            self.llm=llm
        result = self._compute(sample)
        return result

def build_metric():
    return TaskCompletionMetric()

# ==========================================
# 运行测试
# ==========================================
if __name__ == "__main__":
    sample_1 = {
        "task_id": "42966ceff3ff344b",
        "user_query": "帮我点一份张记烤肉店的双人套餐，送到仙林校区1栋，用微信支付",
        "ground_truth": "成功查询店铺和菜品，下达订单并返回订单号。",
        "expected_steps":[
          {"step": 1, "tool_call": "search_restaurants"},
          {"step": 2, "tool_call": "search_products"},
          {"step": 3, "tool_call": "place_order"},
          {"step": 4, "tool_call": "pay_order"}
        ],
        "steps":[
          {"step": 1, "tool_call": "search_restaurants", "observation": "R1001"},
          {"step": 2, "tool_call": "search_products", "observation": "P201"},
          {"step": 3, "tool_call": "place_order", "observation": "ORD-88219"} 
        ],
        "final_answer": "您的订单已成功下达！订单号为 ORD-88219"
    }

    llm = SimpleLLM()
    evaluator = TaskCompletionMetric(llm)
    
    print("开始评估...")
    result = evaluator._compute(sample_1)
    print(result)
    print(f"\n最终得分: {result['score']} ({result['satisfied_weight']} / {result['total_weight']})")
    print("\n详细评判过程:")
    for d in result['details']:
        status = "满足" if d['is_met'] else "未满足"
        print(f"[{status}] (权重: {d['weight']}) 需求: {d['requirement']}")
        print(f"       -> 理由: {d['reasoning']}")