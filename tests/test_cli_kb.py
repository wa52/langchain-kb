import json
from unittest.mock import patch, MagicMock, ANY

import pytest
from click.testing import CliRunner

from src.cli.kb import kb

runner = CliRunner()


class TestCliStructure:

    def test_help_shows_all_commands(self):
        result = runner.invoke(kb, ["--help"])
        assert result.exit_code == 0
        for cmd in ["serve", "index", "search", "chat", "status", "doctor", "config"]:
            assert cmd in result.output

    def test_serve_help(self):
        result = runner.invoke(kb, ["serve", "--help"])
        assert result.exit_code == 0
        assert "--port" in result.output
        assert "--host" in result.output

    def test_index_help(self):
        result = runner.invoke(kb, ["index", "--help"])
        assert result.exit_code == 0
        assert "--path" in result.output
        assert "--rebuild" in result.output
        assert "--dry-run" in result.output

    def test_search_help(self):
        result = runner.invoke(kb, ["search", "--help"])
        assert result.exit_code == 0
        assert "QUERY" in result.output
        assert "--top-k" in result.output

    def test_chat_help(self):
        result = runner.invoke(kb, ["chat", "--help"])
        assert result.exit_code == 0
        assert "--session" in result.output
        assert "--list-sessions" in result.output

    def test_status_help(self):
        result = runner.invoke(kb, ["status", "--help"])
        assert result.exit_code == 0
        assert "--json" in result.output

    def test_doctor_help(self):
        result = runner.invoke(kb, ["doctor", "--help"])
        assert result.exit_code == 0
        assert "--verbose" in result.output

    def test_config_help(self):
        result = runner.invoke(kb, ["config", "--help"])
        assert result.exit_code == 0
        assert "--key" in result.output
        assert "--validate" in result.output


class TestServe:

    def test_serve_starts_uvicorn(self):
        with patch("uvicorn.run") as mock_run:
            result = runner.invoke(kb, ["serve", "--host", "0.0.0.0", "--port", "8080"])
        assert result.exit_code == 0
        mock_run.assert_called_once_with(ANY, host="0.0.0.0", port=8080, log_level="info")

    def test_serve_default_host_port(self):
        with patch("uvicorn.run"):
            result = runner.invoke(kb, ["serve"])
        assert result.exit_code == 0

    def test_serve_json_output(self):
        with patch("uvicorn.run"):
            result = runner.invoke(kb, ["serve", "--json"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["status"] == "ok"
        assert "url" in parsed["data"]


class TestIndex:

    def test_index_default_calls_run_ingestion(self):
        with patch("src.ingestion.pipeline.run_ingestion", return_value=42) as mock_ingest:
            result = runner.invoke(kb, ["index"])
        assert result.exit_code == 0
        mock_ingest.assert_called_once()
        assert "42" in result.output

    def test_index_with_path_calls_run_add_path(self):
        with patch("src.ingestion.pipeline.run_add_path", return_value=5) as mock_add:
            result = runner.invoke(kb, ["index", "--path", "/tmp/test.md"])
        assert result.exit_code == 0
        mock_add.assert_called_once_with("/tmp/test.md", ANY, echo_fn=ANY)
        assert "5" in result.output

    def test_index_rebuild_dry_run_does_not_mutate(self):
        with patch("src.ingestion.pipeline.run_ingestion") as mock_ingest:
            with patch("src.ingestion.pipeline.run_add_path") as mock_add:
                result = runner.invoke(kb, ["index", "--rebuild", "--dry-run"])
        assert result.exit_code == 0
        mock_ingest.assert_not_called()
        mock_add.assert_not_called()
        assert "dry-run" in result.output.lower()

    def test_index_json_output(self):
        with patch("src.ingestion.pipeline.run_ingestion", return_value=10):
            result = runner.invoke(kb, ["index", "--json"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["status"] == "ok"
        assert parsed["data"]["chunks"] == 10

    def test_index_bad_path_returns_error(self):
        with patch("src.ingestion.pipeline.run_add_path", return_value=0):
            result = runner.invoke(kb, ["index", "--path", "/nonexistent"])
        assert result.exit_code != 0

    def test_index_with_chunk_size(self):
        with patch("src.ingestion.pipeline.run_ingestion", return_value=42) as mock_ingest:
            runner.invoke(kb, ["index", "--chunk-size", "300"])
        _, kwargs = mock_ingest.call_args
        assert "chunk_size" in kwargs and kwargs["chunk_size"] == 300


class TestSearch:

    def test_search_returns_results(self):
        mock_docs = [
            MagicMock(metadata={"source": "doc.md"}, page_content="test content"),
        ]
        with patch("src.vector_store.service.VectorStoreService") as mock_vs:
            mock_vs.return_value.get_retriever.return_value.invoke.return_value = mock_docs
            result = runner.invoke(kb, ["search", "test query"])
        assert result.exit_code == 0
        assert "doc.md" in result.output

    def test_search_empty_results_returns_success(self):
        with patch("src.vector_store.service.VectorStoreService") as mock_vs:
            mock_vs.return_value.get_retriever.return_value.invoke.return_value = []
            result = runner.invoke(kb, ["search", "nothing"])
        assert result.exit_code == 0

    def test_search_json_output(self):
        mock_docs = [
            MagicMock(metadata={"source": "doc.md", "chunk_id": "c1"}, page_content="content"),
        ]
        with patch("src.vector_store.service.VectorStoreService") as mock_vs:
            mock_vs.return_value.get_retriever.return_value.invoke.return_value = mock_docs
            result = runner.invoke(kb, ["search", "query", "--json"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["status"] == "ok"
        assert parsed["data"]["total"] == 1
        assert len(parsed["data"]["results"]) > 0

    def test_search_top_k_passed(self):
        with patch("src.vector_store.service.VectorStoreService") as mock_vs:
            runner.invoke(kb, ["search", "query", "--top-k", "3"])
        mock_vs.return_value.get_retriever.assert_called_once_with(k=3)


class TestChat:

    def test_chat_query_returns_answer(self):
        mock_agent = MagicMock()
        with (
            patch("src.agent.rag_agent.create_rag_agent", return_value=mock_agent),
            patch("src.agent.rag_agent.stream_rag_response", return_value=["answer ", "text"]),
        ):
            result = runner.invoke(kb, ["chat", "test question"])
        assert result.exit_code == 0
        assert "answer" in result.output

    def test_chat_list_sessions(self):
        fake_sessions = [
            {"id": "session_1", "created": "2026-07-31 10:00", "title": "Test", "turns": 3},
        ]
        with patch("src.agent.chat_history.list_sessions", return_value=fake_sessions):
            result = runner.invoke(kb, ["chat", "--list-sessions"])
        assert result.exit_code == 0
        assert "Test" in result.output

    def test_chat_with_session_resumes(self):
        mock_history = [{"role": "user", "content": "old question"}]
        with (
            patch("src.agent.chat_history.load_history", return_value=mock_history),
            patch("src.agent.rag_agent.create_rag_agent"),
            patch("src.agent.rag_agent.stream_rag_response", return_value=["answer"]),
        ):
            result = runner.invoke(kb, ["chat", "new question", "--session", "session_1"])
        assert result.exit_code == 0

    def test_chat_session_not_found(self):
        with patch("src.agent.chat_history.load_history", return_value=None):
            result = runner.invoke(kb, ["chat", "q", "--session", "nonexistent"])
        assert result.exit_code != 0

    def test_chat_json_output(self):
        with (
            patch("src.agent.rag_agent.create_rag_agent"),
            patch("src.agent.rag_agent.stream_rag_response", return_value=["full response"]),
        ):
            result = runner.invoke(kb, ["chat", "question", "--json"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["status"] == "ok"
        assert "answer" in parsed["data"]


class TestStatus:

    def test_status_shows_components(self):
        vs_stats = {"count": 100, "source_count": 5, "sources": []}
        with (
            patch("src.vector_store.service.VectorStoreService") as mock_vs,
            patch("src.graph_store.service.GraphService") as mock_gs,
        ):
            mock_vs.return_value.get_stats.return_value = vs_stats
            mock_gs.return_value.get_stats.return_value = {"entities": 20, "relations": 10}
            result = runner.invoke(kb, ["status"])
        assert result.exit_code == 0
        assert "100" in result.output

    def test_status_json_output(self):
        vs_stats = {"count": 50, "source_count": 3, "sources": []}
        with (
            patch("src.vector_store.service.VectorStoreService") as mock_vs,
            patch("src.graph_store.service.GraphService") as mock_gs,
        ):
            mock_vs.return_value.get_stats.return_value = vs_stats
            mock_gs.return_value.get_stats.return_value = {"entities": 5, "relations": 3}
            result = runner.invoke(kb, ["status", "--json"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["status"] == "ok"
        assert parsed["data"]["vector_store"]["count"] == 50


class TestDoctor:

    def test_doctor_runs_checks(self):
        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("src.vector_store.embedding.get_embedding_model"),
            patch("src.vector_store.chroma_client.get_vector_store"),
            patch("src.graph_store.service.GraphService") as mock_gs,
        ):
            mock_gs.return_value.get_entity_count.return_value = 10
            result = runner.invoke(kb, ["doctor"])
        assert result.exit_code == 0
        assert "OK" in result.output

    def test_doctor_detects_failure(self):
        with patch("pathlib.Path.exists", return_value=False):
            result = runner.invoke(kb, ["doctor"])
        assert result.exit_code != 0

    def test_doctor_json_output(self):
        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("src.vector_store.embedding.get_embedding_model"),
            patch("src.vector_store.chroma_client.get_vector_store"),
            patch("src.graph_store.service.GraphService"),
        ):
            result = runner.invoke(kb, ["doctor", "--json"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert "checks" in parsed["data"]


class TestConfig:

    def test_config_shows_keys(self):
        result = runner.invoke(kb, ["config"])
        assert result.exit_code == 0
        assert "DATA_DIR" in result.output
        assert "EMBEDDING_MODEL" in result.output

    def test_config_single_key(self):
        result = runner.invoke(kb, ["config", "--key", "EMBEDDING_MODEL"])
        assert result.exit_code == 0
        assert "EMBEDDING_MODEL" in result.output

    def test_config_validate(self):
        with patch("pathlib.Path.exists", return_value=True):
            result = runner.invoke(kb, ["config", "--validate"])
        assert result.exit_code == 0
        assert "valid" in result.output.lower()

    def test_config_json_output(self):
        result = runner.invoke(kb, ["config", "--json"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["status"] == "ok"
        assert len(parsed["data"]["keys"]) > 0

    def test_config_key_not_found(self):
        result = runner.invoke(kb, ["config", "--key", "NONEXISTENT"])
        assert result.exit_code != 0


class TestExitCodes:

    def test_unknown_command_exit_code_2(self):
        result = runner.invoke(kb, ["nonexistent"])
        assert result.exit_code == 2

    def test_missing_argument_exit_code_2(self):
        result = runner.invoke(kb, ["search"])
        assert result.exit_code == 2
