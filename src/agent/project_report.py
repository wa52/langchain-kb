"""Stage 4: write a generated solution to Markdown project files."""

import json
import time
from datetime import datetime
from pathlib import Path

# Output files: sections → filename
FILE_MAP = {
    "requirement": "requirement.md",
    "solution": "solution.md",
    "algorithm": "algorithm.md",
    "risk": "risk.md",
    "questions": "questions.md",
}


def write_report(project_dir: Path, sections: dict) -> list[str]:
    """Write solution sections to Markdown files under project_dir.

    sections: {filename_key: markdown_content}. Returns sorted file names.
    """
    project_dir = Path(project_dir)
    project_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for key, fname in FILE_MAP.items():
        content = sections.get(key)
        if content is None:
            continue
        (project_dir / fname).write_text(content, encoding="utf-8")
        written.append(fname)
    return sorted(written)


def log_llm_call(project_dir: Path, entry: dict):
    """Append one LLM call record to llm_log.jsonl (summarized, no secrets)."""
    project_dir = Path(project_dir)
    project_dir.mkdir(parents=True, exist_ok=True)
    log_path = project_dir / "llm_log.jsonl"
    record = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "project_name": entry.get("project_name", ""),
        "stage": entry.get("stage", ""),
        "prompt_summary": entry.get("prompt_summary", "")[:200],
        "model": entry.get("model", ""),
        "token_usage": entry.get("token_usage", {}),
        "response_summary": entry.get("response_summary", "")[:200],
        "execution_time_s": round(entry.get("execution_time_s", 0), 3),
        "success": entry.get("success", True),
        "error": entry.get("error", ""),
    }
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def write_check_report(project_dir: Path, check_text: str):
    """Write the optional LLM quality-check report."""
    project_dir = Path(project_dir)
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "check_report.md").write_text(check_text, encoding="utf-8")
