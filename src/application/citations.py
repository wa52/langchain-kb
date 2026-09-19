"""Citation parsing used by chat transports and presentation layers."""

import re


_CITATION_PATTERN = re.compile(r"\[来源:\s*([^\]]{1,256})\]")


def extract_sources(answer: str) -> list[dict]:
    """Extract unique ``[来源: 文件名]`` annotations from an answer."""
    seen: set[str] = set()
    sources: list[dict] = []
    for match in _CITATION_PATTERN.finditer(answer):
        source = match.group(1).strip()
        if source and source not in seen:
            seen.add(source)
            sources.append({"source": source, "chunk_id": "", "excerpt": None})
    return sources
