from unittest.mock import MagicMock

from src.retrieval.grading import grade_document


def test_negative_verdict_is_not_treated_as_relevant():
    llm = MagicMock()
    llm.invoke.return_value.content = "不相关"
    assert grade_document("question", "document", llm) is False


def test_positive_verdict_is_relevant():
    llm = MagicMock()
    llm.invoke.return_value.content = "相关"
    assert grade_document("question", "document", llm) is True
