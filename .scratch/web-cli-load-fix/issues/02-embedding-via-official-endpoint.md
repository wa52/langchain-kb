# 02 — Embedding model loads via official Hugging Face endpoint + pre-warmed cache

**What to build:** The embedding model `BAAI/bge-small-zh-v1.5` must load so that `knowledge web` completes its lifespan and `/api/v1/health` goes ready, and `knowledge cli` loads the agent without a download error. Root cause: `hf-mirror.com` now 308-redirects model files to `huggingface.co`, and `huggingface_hub` rejects that redirect with `FileMetadataError`; the local cache is empty, so there is no fallback. Fix: point `HF_ENDPOINT` at the official endpoint (verified reachable through the user's proxy 127.0.0.1:7892), pre-warm the cache, then document the gotcha in `AGENTS.md`.

**Blocked by:** None — can start immediately

**Status:** ready-for-agent

- [x] `.env`: `HF_ENDPOINT=https://hf-mirror.com` → `https://huggingface.co` (touch only this key, never secrets)
- [x] Pre-warm cache: `hf download BAAI/bge-small-zh-v1.5` succeeds; `~/.cache/huggingface/hub` contains `models--BAAI--bge-small-zh-v1.5`
- [x] `knowledge web` starts; `/api/v1/health` returns ready (smoke-tested with `HF_HUB_OFFLINE=1`: 200, vector_count 109991)
- [ ] `knowledge cli` agent loads without download error; a typed query enters chat
- [x] `AGENTS.md` HF gotcha updated: hf-mirror 308 → official endpoint; recommend `HF_ENDPOINT=https://huggingface.co` when a proxy can reach it; pre-warm with `hf download BAAI/bge-small-zh-v1.5`
- [x] `python -m pytest tests/` green (314 passed; no regression; model-loading tests may run ~15s)