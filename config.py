import os
import sys
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent


def _platform_data_home() -> Path:
    """Platform application data directory for an installed deployment.

    - Windows: %LOCALAPPDATA%/KnowledgeAgent
    - macOS:   ~/Library/Application Support/KnowledgeAgent
    - Linux:   $XDG_DATA_HOME/knowledge-agent or ~/.local/share/knowledge-agent

    Upgrades and re-installs never overwrite user data because the code lives
    in site-packages while the data lives here.
    """
    home = Path.home()
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or (home / "AppData" / "Local"))
        return (base / "KnowledgeAgent").resolve()
    if sys.platform == "darwin":
        return (home / "Library" / "Application Support" / "KnowledgeAgent").resolve()
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg).resolve() if xdg else (home / ".local" / "share")
    return (base / "knowledge-agent").resolve()


def _default_knowledge_home() -> Path:
    """Pick the knowledge-base root.

    Priority:
      1. KNOWLEDGE_HOME env var (explicitly set by the user).
      2. When the package is installed (config.py lives under site-packages),
         default to the platform application data directory so a deployed
         knowledge base survives upgrades and is independent of the working
         directory (see ``_platform_data_home``).
      3. Development checkout: the project root (current behaviour).
    """
    if os.getenv("KNOWLEDGE_HOME"):
        return Path(os.environ["KNOWLEDGE_HOME"]).expanduser().resolve()
    try:
        import sysconfig
        purelib = Path(sysconfig.get_paths()["purelib"]).resolve()
        if str(PROJECT_ROOT).startswith(str(purelib)):
            return _platform_data_home()
    except Exception:
        pass
    return PROJECT_ROOT


def _resolve_dir(key: str, default: str) -> str:
    """Resolve a directory config value; relative paths anchor to KNOWLEDGE_HOME."""
    p = Path(os.getenv(key, default))
    if not p.is_absolute():
        p = KNOWLEDGE_HOME / p
    return str(p)


# Knowledge base home: where .env, chroma_db, data and the knowledge graph live.
# Explicit env wins; installed (wheel) deployments default to the platform
# application data directory; development checkouts default to the project root.
KNOWLEDGE_HOME = _default_knowledge_home()

load_dotenv(KNOWLEDGE_HOME / ".env")

PRODUCT_NAME = os.getenv("PRODUCT_NAME", "个人知识库")
PRODUCT_NAME_EN = os.getenv("PRODUCT_NAME_EN", "Personal Knowledge Base")

DATA_DIR = Path(_resolve_dir("DATA_DIR", "./data/docs"))
CHROMA_PERSIST_DIR = _resolve_dir("CHROMA_PERSIST_DIR", "./chroma_db")
EXTERNAL_DIR = _resolve_dir("EXTERNAL_DIR", "./data/external")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "bge-small-zh")
# Embedding device: "auto" (default) picks GPU when available, else CPU;
# override with "cpu" or "cuda" to force a specific device.
EMBEDDING_DEVICE = os.getenv("EMBEDDING_DEVICE", "auto").lower()
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "500"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "80"))
TOP_K = int(os.getenv("TOP_K", "5"))
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_API_BASE = os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com")

# 评分/压缩用 LLM: "deepseek"（云端）或 "local"（Ollama 本地小模型）
RERANK_LLM = os.getenv("RERANK_LLM", "deepseek").lower()
LOCAL_LLM_BASE = os.getenv("LOCAL_LLM_BASE", "http://127.0.0.1:11434/v1")
LOCAL_LLM_MODEL = os.getenv("LOCAL_LLM_MODEL", "qwen3.5:4b")

# 局域网访问保护: 设置后，非回环(loopback)客户端访问 /api 与 /mcp 必须携带
# `Authorization: Bearer <LAN_TOKEN>`。本机回环访问始终免登录。留空则无保护。
LAN_TOKEN = os.getenv("LAN_TOKEN", "")

# 外部 MCP 客户端配置（opencode 风格 mcp.json，默认 <KNOWLEDGE_HOME>/mcp.json）
MCP_CONFIG_PATH = os.getenv("MCP_CONFIG_PATH", "") or str(
    KNOWLEDGE_HOME / "mcp.json"
)

HF_ENDPOINT = os.getenv("HF_ENDPOINT", "https://huggingface.co")
os.environ["HF_ENDPOINT"] = HF_ENDPOINT
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

ENABLE_GRADING = os.getenv("ENABLE_GRADING", "true").lower() == "true"
ENABLE_REWRITE = os.getenv("ENABLE_REWRITE", "true").lower() == "true"
ENABLE_HYBRID_SEARCH = os.getenv("ENABLE_HYBRID_SEARCH", "true").lower() == "true"
ENABLE_CONTEXT_COMPRESSION = os.getenv("ENABLE_CONTEXT_COMPRESSION", "true").lower() == "true"
ENABLE_GRAPH = os.getenv("ENABLE_GRAPH", "true").lower() == "true"
ENABLE_GRAPH_LLM_EXTRACTION = os.getenv("ENABLE_GRAPH_LLM_EXTRACTION", "false").lower() == "true"
GRAPH_LLM_BATCH_SIZE = int(os.getenv("GRAPH_LLM_BATCH_SIZE", "10"))
GRAPH_LLM_CONCURRENCY = int(os.getenv("GRAPH_LLM_CONCURRENCY", "5"))
GRAPH_PERSIST_DIR = _resolve_dir("GRAPH_PERSIST_DIR", "./data")

# 定时同步的经验库目录（分号分隔的绝对路径；为空则不启用定时同步）。
# 由 sync_experience 原位读取，不做整树复制，仅索引新增/变更的 md/txt/pdf。
EXPERIENCE_DIRS = [
    str((KNOWLEDGE_HOME / d.strip()).resolve()) if not Path(d.strip()).is_absolute() else d.strip()
    for d in os.getenv("EXPERIENCE_DIRS", "").split(";")
    if d.strip()
]
SYNC_INTERVAL_HOURS = float(os.getenv("SYNC_INTERVAL_HOURS", "24"))
MAX_CONTEXT_TOKENS = int(os.getenv("MAX_CONTEXT_TOKENS", "1000"))
# 会话历史上下文管理：超过轮数或估算 token 预算后，把较早的历史压缩成摘要，
# 只把最近 keep_rounds 轮 + 摘要发给 agent（完整历史仍原样保存）。
HISTORY_COMPRESS_ROUNDS = int(os.getenv("HISTORY_COMPRESS_ROUNDS", "10"))
HISTORY_MAX_TOKENS = int(os.getenv("HISTORY_MAX_TOKENS", "4000"))


def ensure_data_dirs():
    """Create the knowledge-base directory skeleton if missing (idempotent)."""
    for d in (DATA_DIR, Path(EXTERNAL_DIR), Path(CHROMA_PERSIST_DIR)):
        d.mkdir(parents=True, exist_ok=True)
