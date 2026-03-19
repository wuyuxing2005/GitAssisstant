import importlib.util
import json
from pathlib import Path
from llm import SimpleLLM
from evaluator import Evaluator
import os
import sys

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


dataset_path = Path(__file__).parent / "data" / "eval_dataset.json"
metric_path_topicAdherence = Path(
    __file__).parent / "metrics" / "1" / "metric.py"
metric_path_taskCompletion = Path(
    __file__).parent / "metrics" / "taskCompletion" / "metric.py"

# 在这里增加你的metric路径
# metric_path_XXX = Path(__file__).parent / "metrics" / "2" / "metric.py"
dataset = load_dataset(dataset_path)
# print(type(dataset[0]))
# 在这里loadn你需要的metric（通过load_metirc(path）
metric_TopicAdherence = load_metric(metric_path_topicAdherence)
metric_taskCompletion =load_metric(metric_path_taskCompletion)
# metric_XXX = load_metric(metric_path_XXX)

# 在metrics里面添加其他的metric       这里添加到[]中->v
evaluator = Evaluator(metrics=[metric_taskCompletion], llm=SimpleLLM())


results = evaluator.evaluate(dataset)

for index, result in enumerate(results, start=1):
    # 在这里进行成绩的打印,每一个metric有自己的key,通过result.get(key)来获取成绩
    # print(index, result.get("topic_adherence"))
    print(index,result.get("task_completion")["score"])