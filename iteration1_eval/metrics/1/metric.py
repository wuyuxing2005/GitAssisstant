import re
from difflib import SequenceMatcher

import numpy as np


REFUSAL_PATTERNS = (
    "cant help",
    "cannot help",
    "cant answer",
    "cannot answer",
    "not able to",
    "wont discuss",
    "out of scope",
    "i must refuse",
    "i refuse",
    "抱歉",
    "不能回答",
    "无法回答",
    "超出范围",
    "拒绝回答",
)

SENTENCE_SPLIT_PATTERN = r"[\n.!?;\u3002\uff01\uff1f\uff1b]"
TOPIC_SPLIT_PATTERN = r",|\uff0c| and | or |/|\u3001|\u548c|\u4ee5\u53ca|\u53ca"
LEADING_CN_PREFIX_PATTERN = (
    r"^(\u8bf7|\u5e2e\u6211|\u544a\u8bc9\u6211|"
    r"\u4ecb\u7ecd\u4e00\u4e0b|\u8bf4\u8bf4|\u804a\u804a|\u5173\u4e8e)"
)
LEADING_EN_PREFIX_PATTERN = (
    r"^(please|can you|could you|tell me about|talk about|discuss|what about)\s+"
)


class TopicAdherenceMetric:
    name = "topic_adherence"

    def __init__(self, mode="f1"):
        self.mode = mode

    def score(self, sample, llm=None):
        del llm

        messages = self._build_messages(sample)
        reference_topics = self._get_reference_topics(sample, messages)
        topics = self._extract_topics(sample, messages)

        if not topics:
            return float("nan")

        topic_answered = self._check_topics_answered(messages, topics)
        topic_classifications = self._classify_topics(reference_topics, topics)

        return float(self._compute_score(topic_answered, topic_classifications))

    def _build_messages(self, sample):
        if isinstance(sample.get("messages"), list):
            return sample["messages"]
        if isinstance(sample.get("user_input"), list):
            return sample["user_input"]
        return [
            {"role": "human", "content": str(
                sample.get("user_query", "")).strip()},
            {"role": "ai", "content": str(
                sample.get("final_answer", "")).strip()},
        ]

    def _get_reference_topics(self, sample, messages):
        if sample.get("reference_topics"):
            return self._normalize_topic_list(sample["reference_topics"])

        human_topics = []
        if sample.get("user_query"):
            human_topics.extend(self._extract_topics_from_text(
                str(sample["user_query"])))

        for message in messages:
            if str(message.get("role", "")).lower() in {"human", "user"}:
                human_topics.extend(
                    self._extract_topics_from_text(
                        str(message.get("content", "")))
                )

        return self._normalize_topic_list(human_topics)

    def _extract_topics(self, sample, messages):
        if sample.get("topics"):
            return self._normalize_topic_list(sample["topics"])

        topics = []
        seen = set()

        for message in messages:
            if str(message.get("role", "")).lower() not in {"human", "user"}:
                continue

            for topic in self._extract_topics_from_text(str(message.get("content", ""))):
                normalized = self._normalize_text(topic)
                if normalized and normalized not in seen:
                    seen.add(normalized)
                    topics.append(topic)

        return topics

    def _extract_topics_from_text(self, text):
        clauses = re.split(SENTENCE_SPLIT_PATTERN, text.strip())
        topics = []

        for clause in clauses:
            clause = clause.strip()
            if not clause:
                continue

            clause = re.sub(LEADING_EN_PREFIX_PATTERN, "",
                            clause, flags=re.IGNORECASE)
            clause = re.sub(LEADING_CN_PREFIX_PATTERN, "", clause)

            for part in re.split(TOPIC_SPLIT_PATTERN, clause):
                topic = part.strip(" .,:;!?")
                if len(self._normalize_text(topic)) >= 2:
                    topics.append(topic)

        return topics

    def _normalize_topic_list(self, topics):
        normalized_topics = []
        seen = set()

        for topic in topics:
            topic_text = str(topic).strip()
            normalized = self._normalize_text(topic_text)
            if normalized and normalized not in seen:
                seen.add(normalized)
                normalized_topics.append(topic_text)

        return normalized_topics

    def _check_topics_answered(self, messages, topics):
        turns = self._build_turns(messages)
        verdicts = []

        for topic in topics:
            answered = False
            refused = False

            for human_text, ai_text in turns:
                if not self._texts_related(topic, human_text):
                    continue

                turn_answered, turn_refused = self._classify_turn_response(
                    topic, ai_text)
                answered = answered or turn_answered
                refused = refused or turn_refused

            verdicts.append(answered and not refused)

        return np.array(verdicts, dtype=bool)

    def _build_turns(self, messages):
        turns = []
        current_human = None
        current_ai_parts = []

        for message in messages:
            role = str(message.get("role", "")).lower()
            content = str(message.get("content", "")).strip()

            if role in {"human", "user"}:
                if current_human is not None:
                    turns.append(
                        (current_human, "\n".join(current_ai_parts).strip()))
                current_human = content
                current_ai_parts = []
                continue

            if role in {"ai", "assistant"} and current_human is not None:
                current_ai_parts.append(content)

        if current_human is not None:
            turns.append((current_human, "\n".join(current_ai_parts).strip()))

        return turns

    def _classify_turn_response(self, topic, ai_text):
        if not ai_text:
            return False, False

        topic_related_sentences = [
            sentence
            for sentence in self._split_sentences(ai_text)
            if self._texts_related(topic, sentence)
        ]

        if not topic_related_sentences:
            if self._contains_refusal(ai_text):
                return False, True
            return True, False

        answered = any(
            not self._contains_refusal(sentence) for sentence in topic_related_sentences
        )
        refused = any(
            self._contains_refusal(sentence) for sentence in topic_related_sentences
        )
        return answered, refused

    def _split_sentences(self, text):
        return [
            segment.strip()
            for segment in re.split(SENTENCE_SPLIT_PATTERN, text)
            if segment.strip()
        ]

    def _contains_refusal(self, text):
        normalized = self._normalize_text(text)
        return any(pattern in normalized for pattern in REFUSAL_PATTERNS)

    def _classify_topics(self, reference_topics, topics):
        classifications = [
            any(self._texts_related(topic, reference)
                for reference in reference_topics)
            for topic in topics
        ]
        return np.array(classifications, dtype=bool)

    def _texts_related(self, left, right):
        left_normalized = self._normalize_text(left)
        right_normalized = self._normalize_text(right)

        if not left_normalized or not right_normalized:
            return False
        if left_normalized == right_normalized:
            return True
        if left_normalized in right_normalized or right_normalized in left_normalized:
            return True

        return SequenceMatcher(None, left_normalized, right_normalized).ratio() >= 0.6

    def _normalize_text(self, text):
        lowered = text.casefold()
        lowered = re.sub(r"[\"'`“”‘’]", "", lowered)
        lowered = re.sub(r"\s+", " ", lowered)
        lowered = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff ]+", " ", lowered)
        return lowered.strip()

    def _compute_score(self, topic_answered, topic_classifications):
        true_positives = np.sum(topic_answered & topic_classifications)
        false_positives = np.sum(topic_answered & ~topic_classifications)
        false_negatives = np.sum(~topic_answered & topic_classifications)
        eps = 1e-10

        if self.mode == "precision":
            return true_positives / (true_positives + false_positives + eps)
        if self.mode == "recall":
            return true_positives / (true_positives + false_negatives + eps)

        precision = true_positives / (true_positives + false_positives + eps)
        recall = true_positives / (true_positives + false_negatives + eps)
        return 2 * (precision * recall) / (precision + recall + eps)


def build_metric():
    return TopicAdherenceMetric()
