from src.application.query import QueryService
from src.domain.models import DocumentChunk, Query, RetrievalResult


class FakeRetriever:
    def __init__(self):
        self.queries = []

    def retrieve(self, query):
        self.queries.append(query)
        return [RetrievalResult(DocumentChunk("answer", source="note.md"), rank=1)]


def test_query_service_uses_project_owned_retriever_port():
    retriever = FakeRetriever()
    result = QueryService(retriever).search("hello", limit=3, capability="python")
    assert result[0].chunk.source == "note.md"
    assert retriever.queries == [Query("hello", 3, "python")]
