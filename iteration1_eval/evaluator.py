class Evaluator:

    def __init__(self, metrics, llm):
        self.metrics = metrics
        self.llm = llm

    def evaluate(self, dataset):

        results = []
        # print("dataset[0] type:", type(dataset[0]))
        # print("dataset[0] content:", dataset[0])
        index = 0
        for sample in dataset:
            sample_result = {}

            for metric in self.metrics:
                # print(type(sample))
                score = metric.score(sample, self.llm)
                print(f"No.{index} Metric: {metric.name} finished")
                sample_result[metric.name] = score
            index += 1
            results.append(sample_result)

        return results
