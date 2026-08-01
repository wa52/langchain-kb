from functools import lru_cache

from langchain_huggingface import HuggingFaceEmbeddings
from config import EMBEDDING_MODEL, EMBEDDING_DEVICE


def resolve_embedding_device() -> str:
    """Pick the embedding device: GPU when available, otherwise CPU."""
    forced = EMBEDDING_DEVICE
    if forced in ("cpu", "cuda"):
        return forced
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda"
    except Exception:
        pass
    return "cpu"


@lru_cache(maxsize=1)
def get_embedding_model():
    if EMBEDDING_MODEL == "openai":
        from langchain_openai import OpenAIEmbeddings
        return OpenAIEmbeddings(model="text-embedding-3-small")
    model_map = {
        "bge-m3": "BAAI/bge-m3",
        "bge-small-zh": "BAAI/bge-small-zh-v1.5",
        "bge-base-zh": "BAAI/bge-base-zh-v1.5",
    }
    model_name = model_map.get(EMBEDDING_MODEL, EMBEDDING_MODEL)
    return HuggingFaceEmbeddings(
        model_name=model_name,
        model_kwargs={"device": resolve_embedding_device()},
        encode_kwargs={"normalize_embeddings": True, "batch_size": 32},
    )
