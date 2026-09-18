from unittest.mock import MagicMock, patch


def test_managed_retriever_is_reused_for_unfiltered_queries():
    from src.application.knowledge import retrieve_documents

    retriever = MagicMock()
    retriever.invoke.return_value = ["doc"]
    manager = MagicMock()
    manager.is_ready.return_value = True
    manager.get_retriever.return_value = retriever

    with (
        patch("src.resources.ResourceManager.get_instance", return_value=manager),
        patch("src.vector_store.service.VectorStoreService") as service,
    ):
        result = retrieve_documents("标定", 6)

    assert result == ["doc"]
    manager.get_retriever.assert_called_once_with(k=6)
    retriever.invoke.assert_called_once_with("标定")
    service.assert_not_called()


def test_capability_filter_uses_scoped_retriever():
    from src.application.knowledge import retrieve_documents

    retriever = MagicMock()
    retriever.invoke.return_value = ["filtered"]
    service = MagicMock()
    service.get_retriever.return_value = retriever

    with patch("src.vector_store.service.VectorStoreService", return_value=service):
        result = retrieve_documents("测量", 4, capability="2")

    assert result == ["filtered"]
    service.get_retriever.assert_called_once_with(k=4, capability="2")
