from functools import lru_cache
from huggingface_hub import constants as hf_constants

# Force HF to use mirror and disable symlinks
import os
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

from langchain_huggingface import HuggingFaceEmbeddings
from config import EMBEDDING_MODEL


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
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True, "batch_size": 32},
    )
