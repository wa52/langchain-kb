import hashlib
import json
import asyncio

import pytest


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def test_source_health_audit_classifies_tracked_records_without_leaking_root_or_content(tmp_path):
    from src.application.source_health import SourceHealthAuditor

    root = tmp_path / "knowledge-root"
    root.mkdir()
    (root / "healthy.md").write_bytes(b"healthy source")
    (root / "changed.md").write_bytes(b"new content")
    (root / "copy-a.md").write_bytes(b"duplicate content")
    (root / "copy-b.md").write_bytes(b"duplicate content")
    records = [
        {"source_type": "external", "file_key": "healthy.md", "hash": _digest(b"healthy source")},
        {"source_type": "external", "file_key": "changed.md", "hash": _digest(b"old content")},
        {"source_type": "external", "file_key": "missing.md", "hash": _digest(b"missing")},
        {"source_type": "external", "file_key": "copy-a.md", "hash": _digest(b"duplicate content")},
        {"source_type": "external", "file_key": "copy-b.md", "hash": _digest(b"duplicate content")},
        {"source_type": "unknown-secret-root", "file_key": str(root / "private.md"), "hash": "abc"},
    ]
    progress = []
    auditor = SourceHealthAuditor(
        list_sources=lambda: records,
        source_roots={"external": root},
        hash_file=lambda path: _digest(path.read_bytes()),
    )

    result = auditor.run(progress=lambda checked, total: progress.append((checked, total)))

    assert result["summary"] == {
        "total": 6,
        "checked": 6,
        "healthy": 1,
        "missing": 1,
        "changed": 1,
        "duplicate_files": 2,
        "unreadable": 0,
        "unresolved": 1,
        "issues_total": 5,
    }
    by_key = {item["file_key"]: item for item in result["issues"]}
    assert by_key["changed.md"]["status"] == "changed"
    assert by_key["missing.md"]["status"] == "missing"
    assert by_key["copy-a.md"]["duplicate_count"] == 1
    assert next(
        item for item in result["issues"] if item["source_type"] == "unknown-secret-root"
    )["status"] == "unresolved"
    serialized = json.dumps(result)
    assert str(root) not in serialized
    assert "duplicate content" not in serialized
    assert progress[-1] == (6, 6)


def test_source_health_audit_detects_symlink_escape_without_reading_outside(tmp_path):
    import pytest

    from src.application.source_health import SourceHealthAuditor

    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()
    outside_file = outside / "secret.md"
    outside_file.write_bytes(b"private")
    link = allowed / "escape.md"
    try:
        link.symlink_to(outside_file)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlinks unavailable: {exc}")

    auditor = SourceHealthAuditor(
        list_sources=lambda: [{
            "source_type": "external", "file_key": "escape.md", "hash": _digest(b"private"),
        }],
        source_roots={"external": allowed},
        hash_file=lambda path: _digest(path.read_bytes()),
    )

    result = auditor.run()

    assert result["issues"][0]["status"] == "unresolved"
    assert str(outside_file) not in json.dumps(result)


def test_source_health_audit_rejects_parent_path_escape_before_hashing(tmp_path):
    from src.application.source_health import SourceHealthAuditor

    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()
    (outside / "secret.md").write_bytes(b"private")
    hash_calls = []
    auditor = SourceHealthAuditor(
        list_sources=lambda: [{
            "source_type": "external", "file_key": "../outside/secret.md", "hash": _digest(b"private"),
        }],
        source_roots={"external": allowed},
        hash_file=lambda path: hash_calls.append(path) or _digest(path.read_bytes()),
    )

    result = auditor.run()

    assert result["issues"][0]["status"] == "unresolved"
    assert hash_calls == []
    assert str(outside) not in json.dumps(result)


def test_source_health_task_manager_rejects_overlapping_audits():
    from src.api.services.source_health import SourceHealthTaskManager

    manager = SourceHealthTaskManager()
    manager.create_task()

    with pytest.raises(RuntimeError, match="正在运行"):
        manager.create_task()


def test_source_health_background_task_reports_progress_and_result(monkeypatch):
    from src.api.services import source_health

    manager = source_health.get_source_health_task_manager()
    manager.clear()
    task_id = manager.create_task()

    class FakeAuditor:
        def run(self, *, progress):
            progress(1, 2)
            progress(2, 2)
            return {
                "summary": {"total": 2},
                "issues": [],
                "issues_truncated": False,
            }

    monkeypatch.setattr(
        "src.bootstrap.composition.create_source_health_auditor",
        lambda: FakeAuditor(),
    )
    asyncio.run(source_health.run_source_health_task(task_id))

    task = manager.get_task(task_id)
    assert task["status"] == "done"
    assert task["progress"] == {"checked": 2, "total": 2}
    assert task["result"]["summary"]["total"] == 2
    manager.clear()


def test_current_source_health_adapter_maps_internal_external_and_experience_roots(tmp_path, monkeypatch):
    import config
    from src.adapters.ingestion.source_health import create_current_source_health_auditor
    from src.ingestion.pipeline import _experience_namespace
    from src.ingestion.tracker import get_file_hash

    internal = tmp_path / "internal"
    external = tmp_path / "external"
    experience = tmp_path / "experience"
    for root in (internal, external, experience):
        root.mkdir()
    sources = [
        ("internal", internal, "manual.md"),
        ("external", external, "upload.md"),
        (f"experience:{_experience_namespace(experience)}", experience, "project.md"),
    ]
    records = []
    content_by_source = {"internal": b"shared", "external": b"shared", sources[2][0]: b"experience"}
    for source_type, root, name in sources:
        (root / name).write_bytes(content_by_source[source_type])
        records.append({
            "source_type": source_type,
            "file_key": name,
            "hash": get_file_hash(str(root / name)),
        })
    monkeypatch.setattr(config, "DATA_DIR", internal)
    monkeypatch.setattr(config, "EXTERNAL_DIR", external)
    monkeypatch.setattr(config, "EXPERIENCE_DIRS", [str(experience)])
    monkeypatch.setattr("src.ingestion.tracker.snapshot_tracker", lambda: {
        source_type: {record["file_key"]: record["hash"]}
        for source_type, record in zip((item[0] for item in sources), records)
    })

    result = create_current_source_health_auditor().run()

    assert result["summary"]["total"] == 3
    assert result["summary"]["healthy"] == 1
    assert result["summary"]["duplicate_files"] == 2
    assert {item["status"] for item in result["issues"]} == {"duplicate"}
