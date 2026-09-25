"""Bridge source-health use cases to the current tracker and config."""

from pathlib import Path


def create_current_source_health_auditor():
    from config import DATA_DIR, EXTERNAL_DIR, EXPERIENCE_DIRS
    from src.application.source_health import SourceHealthAuditor
    from src.ingestion.pipeline import _experience_namespace
    from src.ingestion.tracker import get_file_hash, snapshot_tracker

    roots = {
        "internal": Path(DATA_DIR),
        "external": Path(EXTERNAL_DIR),
    }
    for configured_dir in EXPERIENCE_DIRS:
        root = Path(configured_dir)
        roots[f"experience:{_experience_namespace(root)}"] = root

    def list_sources():
        tracker = snapshot_tracker()
        return [
            {"source_type": source_type, "file_key": file_key, "hash": digest}
            for source_type, registry in tracker.items()
            if isinstance(registry, dict)
            for file_key, digest in registry.items()
        ]

    return SourceHealthAuditor(
        list_sources=list_sources,
        source_roots=roots,
        hash_file=lambda path: get_file_hash(str(path)),
    )
