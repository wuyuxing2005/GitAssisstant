class Evaluator:

    def __init__(self, metrics, llm):
        self.metrics = metrics
        self.llm = llm

    def evaluate(self, dataset):

        results = []

        for sample in dataset:

            sample_result = {}

            for metric in self.metrics:

                score = metric.score(sample, self.llm)

                sample_result[metric.name] = score

            results.append(sample_result)

        return results
