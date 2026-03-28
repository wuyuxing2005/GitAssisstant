import importlib.util
import json
import os
import sys
import csv
from pathlib import Path

from evaluator import Evaluator
from llm import SimpleLLM


current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)


def load_dataset(dataset_path):
    with open(dataset_path, "r", encoding="utf-8") as file:
        return json.load(file)


def load_metric(metric_path):
    spec = importlib.util.spec_from_file_location("metric_module", metric_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"failed to load metric module from {metric_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build_metric()


def extract_score(metric_result):
    if isinstance(metric_result, dict):
        return metric_result.get("score")
    return metric_result


dataset_path = Path(__file__).parent / "data" / "eval_dataset.json"
metric_path_topic_adherence = Path(
    __file__).parent / "metrics" / "topicAdherence" / "metric.py"
metric_path_task_completion = Path(
    __file__).parent / "metrics" / "taskCompletion" / "metric.py"
metric_path_tool_call_f1 = Path(
    __file__).parent / "metrics" / "toolCallF1" / "metric.py"
metric_path_planning_rationality=Path(
    __file__).parent / "metrics" / "planningRationality" / "metric.py"
# TODO
# 在这里添加你的metric路径，例如：
# metric_path_your_metric = Path(__file__).parent / "metrics" / "your_metric" / "metric.py"

csv_output_path = Path(__file__).parent / "output" / "eval_results.csv"

dataset = load_dataset(dataset_path)
metric_topic_adherence = load_metric(metric_path_topic_adherence)
metric_task_completion = load_metric(metric_path_task_completion)
metric_tool_call_f1 = load_metric(metric_path_tool_call_f1)
metric_planning_rationality = load_metric(metric_path_planning_rationality)

# TODO
# 在这里添加你的metric加载，例如：
# metric_your_metric = load_metric(metric_path_your_metric)

enabled_metrics = [metric_tool_call_f1,
                   metric_topic_adherence, metric_task_completion,metric_planning_rationality  # TODO ,metric_your_metric
                   ]

evaluator = Evaluator(metrics=enabled_metrics, llm=SimpleLLM())
print("Starting evaluation. Results will be printed to the terminal and saved to a CSV file.")
results = evaluator.evaluate(dataset)

header = ["index"] + [metric.name for metric in enabled_metrics]
csv_rows = [header]

for index, result in enumerate(results, start=1):
    row = [str(index)]
    for metric in enabled_metrics:
        score = extract_score(result.get(metric.name))
        row.append("" if score is None else str(score))
    csv_rows.append(row)

with open(csv_output_path, "w", newline="", encoding="utf-8-sig") as csv_file:
    writer = csv.writer(csv_file)
    writer.writerows(csv_rows)

print(f"Evaluation completed. Results have been saved to: {csv_output_path}")
