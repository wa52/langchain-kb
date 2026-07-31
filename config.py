import os
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent


def _resolve_dir(key: str, default: str) -> str:
    """Resolve a directory config value; relative paths anchor to KNOWLEDGE_HOME."""
    p = Path(os.getenv(key, default))
    if not p.is_absolute():
        p = KNOWLEDGE_HOME / p
    return str(p)


# Knowledge base home: where .env, chroma_db, data and the knowledge graph live.
# Defaults to the project root so commands work from any working directory.
KNOWLEDGE_HOME = Path(os.getenv("KNOWLEDGE_HOME", str(PROJECT_ROOT))).expanduser().resolve()

load_dotenv(KNOWLEDGE_HOME / ".env")

PRODUCT_NAME = os.getenv("PRODUCT_NAME", "个人知识库")
PRODUCT_NAME_EN = os.getenv("PRODUCT_NAME_EN", "Personal Knowledge Base")

DATA_DIR = Path(_resolve_dir("DATA_DIR", "./data/docs"))
CHROMA_PERSIST_DIR = _resolve_dir("CHROMA_PERSIST_DIR", "./chroma_db")
EXTERNAL_DIR = _resolve_dir("EXTERNAL_DIR", "./data/external")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "bge-small-zh")
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "500"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "80"))
TOP_K = int(os.getenv("TOP_K", "5"))
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_API_BASE = os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com")

HF_ENDPOINT = os.getenv("HF_ENDPOINT", "https://hf-mirror.com")
os.environ["HF_ENDPOINT"] = HF_ENDPOINT
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

ENABLE_GRADING = os.getenv("ENABLE_GRADING", "true").lower() == "true"
ENABLE_REWRITE = os.getenv("ENABLE_REWRITE", "true").lower() == "true"
ENABLE_HYBRID_SEARCH = os.getenv("ENABLE_HYBRID_SEARCH", "true").lower() == "true"
ENABLE_CONTEXT_COMPRESSION = os.getenv("ENABLE_CONTEXT_COMPRESSION", "true").lower() == "true"
ENABLE_GRAPH = os.getenv("ENABLE_GRAPH", "true").lower() == "true"
ENABLE_GRAPH_LLM_EXTRACTION = os.getenv("ENABLE_GRAPH_LLM_EXTRACTION", "false").lower() == "true"
GRAPH_LLM_BATCH_SIZE = int(os.getenv("GRAPH_LLM_BATCH_SIZE", "10"))
GRAPH_PERSIST_DIR = _resolve_dir("GRAPH_PERSIST_DIR", "./data")
MAX_CONTEXT_TOKENS = int(os.getenv("MAX_CONTEXT_TOKENS", "1000"))


def ensure_data_dirs():
    """Create the knowledge-base directory skeleton if missing (idempotent)."""
    for d in (DATA_DIR, Path(EXTERNAL_DIR), Path(CHROMA_PERSIST_DIR)):
        d.mkdir(parents=True, exist_ok=True)
