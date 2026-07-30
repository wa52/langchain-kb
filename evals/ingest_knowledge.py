import os
os.environ["DATA_DIR"] = str(Path(__file__).parent / "knowledge")
os.environ["CHROMA_PERSIST_DIR"] = "./chroma_db"

from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ingestion.pipeline import run_add_path
from src.ingestion.tracker import clear_tracker

knowledge_dir = Path(__file__).parent / "knowledge"
clear_tracker()
run_add_path(str(knowledge_dir), echo_fn=print)
print("Done!")
