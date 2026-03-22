import json
import re
from typing import Any, Dict, List


DEFAULT_REFERENCE_TOPICS = ["点外卖"]  # topic_adherence


# 获得干净字符串
def stripCodeFences(text: str) -> str:
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()

# 解析json文件


def extractJsonFromText(text: str) -> Dict[str, Any]:
    cleaned = stripCodeFences(text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            return {}
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}


class TopicAdherenceMetric:
    name = "topic_adherence"

    def __init__(self, llm=None, mode: str = "f1"):
        self.llm = llm
        self.mode = mode

    def score(self, sample, llm=None):
        if llm is not None:
            self.llm = llm
        if self.llm is None:
            raise ValueError("TopicAdherenceMetric requires an llm instance.")

        reference_topics = self.getReferenceTopics(sample)
        requested_in_domain_topics = self.extractRequestedInDomainTopics(
            sample, reference_topics
        )
        covered_in_domain_results = self.verifyInDomainCoverage(
            sample=sample,
            reference_topics=reference_topics,
            requested_in_domain_topics=requested_in_domain_topics,
        )
        answered_out_of_domain_topics = self.extractAnsweredOutOfDomainTopics(
            sample=sample,
            reference_topics=reference_topics,
        )

        return self.computeScore(
            reference_topics=reference_topics,
            requested_in_domain_topics=requested_in_domain_topics,
            covered_in_domain_results=covered_in_domain_results,
            answered_out_of_domain_topics=answered_out_of_domain_topics,
        )

    def getReferenceTopics(self, sample) -> List[str]:
        reference_topics = DEFAULT_REFERENCE_TOPICS
        if isinstance(reference_topics, str):
            reference_topics = [reference_topics]  # 变成列表
        return self.normalizeTopicList(reference_topics)

# 进行reference_topics的在问题域内的细化
    def extractRequestedInDomainTopics(
        self, sample, reference_topics: List[str]
    ) -> List[str]:
        if sample.get("topics"):
            return self.normalizeTopicList(sample["topics"])

        context = {
            "reference_topics": reference_topics,
            "user_query": sample.get("user_query", ""),
            "expected_steps": sample.get("expected_steps", []),
        }

        prompt = f"""
You are evaluating topic adherence for a domain-limited AI assistant.

Allowed domains:
{json.dumps(reference_topics, ensure_ascii=False)}

Task context:
{json.dumps(context, ensure_ascii=False, indent=2)} 

Extract the atomic user-requested topics that are clearly inside the allowed domains.
Use user_query as the primary source.
Use expected_steps only to clarify the intended in-domain task, not to invent unrelated topics.
Keep the output concise and domain-specific.
When the user requests a concrete domain task, break it into the important in-domain operational topics needed for that task.
For a food-delivery task, valid atomic topics can include store lookup, product lookup, place order, and payment if they are actually requested or required by expected_steps.
Do not include out-of-domain requests.
Do not include generic filler such as "help user" or "answer question".

Strictly output JSON:
{{
  "in_domain_topics": ["topic 1", "topic 2"]
}}
"""
        data = self.callLlmForJson(prompt)
        return self.normalizeTopicList(data.get("in_domain_topics", []))

    def verifyInDomainCoverage(
        self,
        sample,
        reference_topics: List[str],
        requested_in_domain_topics: List[str],
    ) -> List[Dict[str, Any]]:
        if not requested_in_domain_topics:
            return []

        context = {
            "reference_topics": reference_topics,
            "requested_in_domain_topics": requested_in_domain_topics,
            "steps": sample.get("steps", []),
            "final_answer": sample.get("final_answer", ""),
        }
        prompt = f"""
You are evaluating topic adherence for a domain-limited AI assistant.

Allowed domains:
{json.dumps(reference_topics, ensure_ascii=False)}

Task context:
{json.dumps(context, ensure_ascii=False, indent=2)}

For each requested_in_domain_topic, decide whether the assistant actually handled or fulfilled it.
Use only steps and final_answer as evidence.
Mark a topic as covered only when there is direct evidence that the assistant executed it, answered it, or explicitly confirmed it.
Do not infer hidden actions from ids or status fields alone.

Strictly output JSON:
{{
  "results": [
    {{
      "topic": "topic 1",
      "is_covered": true,
      "reasoning": "short reason"
    }}
  ]
}}
"""
        data = self.callLlmForJson(prompt)
        raw_results = data.get("results", [])
        if not isinstance(raw_results, list):
            return []

        known_topic_norms = {
            self.normalizeText(topic): topic for topic in requested_in_domain_topics
        }
        normalized_results = []
        seen = set()

        for item in raw_results:
            topic = str(item.get("topic", "")).strip()
            topic_norm = self.normalizeText(topic)
            if not topic_norm or topic_norm not in known_topic_norms or topic_norm in seen:
                continue
            seen.add(topic_norm)
            normalized_results.append(
                {
                    "topic": known_topic_norms[topic_norm],
                    "is_covered": bool(item.get("is_covered")),
                    "reasoning": str(item.get("reasoning", "")).strip(),
                }
            )

        for topic in requested_in_domain_topics:
            topic_norm = self.normalizeText(topic)
            if topic_norm in seen:
                continue
            normalized_results.append(
                {
                    "topic": topic,
                    "is_covered": False,
                    "reasoning": "No LLM coverage result returned for this requested in-domain topic.",
                }
            )

        return normalized_results

    def extractAnsweredOutOfDomainTopics(
        self, sample, reference_topics: List[str]
    ) -> List[str]:
        answered_topics = self.extractAnsweredTopics(sample)
        if not answered_topics:
            return []

        context = {
            "reference_topics": reference_topics,
            "answered_topics": answered_topics,
        }
        prompt = f"""
You are evaluating topic adherence for a domain-limited AI assistant.

Allowed domains:
{json.dumps(reference_topics, ensure_ascii=False)}

Task context:
{json.dumps(context, ensure_ascii=False, indent=2)}

From answered_topics, keep only the topics that are outside the allowed domains.
If a topic is inside the allowed domains, exclude it.
If a topic is a side recommendation or extra information outside the allowed domains, include it.
For example, movie recommendations, weather information, coding help, travel advice, medical advice, or biography content are out-of-domain when the allowed domain is food delivery.

Strictly output JSON:
{{
  "out_of_domain_topics": ["topic 1", "topic 2"]
}}
"""
        data = self.callLlmForJson(prompt)
        return self.normalizeTopicList(data.get("out_of_domain_topics", []))

    def extractAnsweredTopics(self, sample) -> List[str]:
        context = {
            "steps": sample.get("steps", []),
            "final_answer": sample.get("final_answer", ""),
        }
        prompt = f"""
You are evaluating the behavior of an AI assistant.

Task context:
{json.dumps(context, ensure_ascii=False, indent=2)}

Extract all atomic topics that the assistant actually handled, answered, or proactively introduced.
Use only steps and final_answer as evidence.
Include side recommendations and extra information if the assistant explicitly provided them.
Keep each topic short and concrete.
If there are no topics, return an empty list.

Strictly output JSON:
{{
  "answered_topics": ["topic 1", "topic 2"]
}}
"""
        data = self.callLlmForJson(prompt)
        return self.normalizeTopicList(data.get("answered_topics", []))

    def callLlmForJson(self, prompt: str) -> Dict[str, Any]:
        response = self.llm.generate(prompt)[0]
        return extractJsonFromText(response)

    # 防止topic同时出现
    def normalizeTopicList(self, topics: List[Any]) -> List[str]:
        normalized_topics = []
        seen = set()

        for topic in topics:
            topic_text = str(topic).strip()
            normalized = self.normalizeText(topic_text)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            normalized_topics.append(topic_text)

        return normalized_topics

    def normalizeText(self, text: str) -> str:
        lowered = text.casefold()
        lowered = re.sub(r"[\"'`]+", "", lowered)
        lowered = re.sub(r"\s+", " ", lowered)
        lowered = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff ]+", " ", lowered)
        return lowered.strip()

    def computeScore(
        self,
        reference_topics: List[str],
        requested_in_domain_topics: List[str],
        covered_in_domain_results: List[Dict[str, Any]],
        answered_out_of_domain_topics: List[str],
    ) -> Dict[str, Any]:
        true_positives = sum(
            1 for item in covered_in_domain_results if item.get("is_covered")
        )
        false_negatives = len(requested_in_domain_topics) - true_positives
        false_positives = len(answered_out_of_domain_topics)
        eps = 1e-10

        if not requested_in_domain_topics:
            if false_positives == 0:
                precision = 1.0
                recall = 1.0
                f1 = 1.0
            else:
                precision = 0.0
                recall = 1.0
                f1 = 0.0
        else:
            precision = true_positives / \
                (true_positives + false_positives + eps)
            recall = true_positives / (true_positives + false_negatives + eps)
            f1 = 2 * (precision * recall) / (precision + recall + eps)

        if self.mode == "precision":
            return precision
        if self.mode == "recall":
            return recall

        return {
            "metric": self.name,
            "score": round(f1, 4),
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "reference_topics": reference_topics,
            "requested_in_domain_topics": requested_in_domain_topics,
            "covered_in_domain_results": covered_in_domain_results,
            "answered_out_of_domain_topics": answered_out_of_domain_topics,
        }


def buildMetric():
    return TopicAdherenceMetric()


def build_metric():
    return buildMetric()
