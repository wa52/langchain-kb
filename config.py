import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

DATA_DIR = Path(os.getenv("DATA_DIR", r"C:\Users\SJ\Desktop\md\langchain_data"))
CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", "./chroma_db")
EXTERNAL_DIR = os.getenv("EXTERNAL_DIR", "./data/external")
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
GRAPH_PERSIST_DIR = os.getenv("GRAPH_PERSIST_DIR", "./data")
MAX_CONTEXT_TOKENS = int(os.getenv("MAX_CONTEXT_TOKENS", "1000"))

DATA_DIR = Path(DATA_DIR)
if not DATA_DIR.is_absolute():
    DATA_DIR = Path.cwd() / DATA_DIR
