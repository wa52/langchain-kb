from src.application.intent_prototypes import IntentPrototypeClassifier


def test_intent_prototypes_cache_examples_and_classify_query():
    calls = []
    def embed(texts):
        calls.append(texts)
        return [[1.0, 0.0] if "GitHub" in text or "issue" in text else [0.0, 1.0] for text in texts]
    classifier = IntentPrototypeClassifier(embed)
    scores = classifier.classify("帮我创建 GitHub issue")
    classifier.classify("帮我创建 GitHub issue")
    assert scores["agent"] > scores["direct"]
    assert len(calls) == 3  # prototypes once, then one query vector per decision


def test_intent_prototypes_compare_two_topics_with_cosine_similarity():
    classifier = IntentPrototypeClassifier(lambda texts: [[1.0, 0.0] if "HALCON" in text else [0.0, 1.0] for text in texts])
    assert classifier.similarity("HALCON 参数", "HALCON 标定") == 1.0
    assert classifier.similarity("今天吃什么", "HALCON 标定") == 0.0
