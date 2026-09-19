from src.application.source_enrichment import enrich_sources


def test_enrich_sources_keeps_citations_and_adds_retrieval_metadata():
    result = enrich_sources(
        "answer",
        extract_sources=lambda _: [{"source": "guide.md"}],
        source_lookup=lambda _: {"chunk_id": "c1", "excerpt": "text"},
        hit_chain=lambda: ["vector", "bm25"],
    )

    assert result == [{
        "source": "guide.md",
        "chunk_id": "c1",
        "excerpt": "text",
        "hit_chain": ["vector", "bm25"],
    }]
