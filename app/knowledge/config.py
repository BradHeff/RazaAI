import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

KNOWLEDGE_DIR = Path(os.getenv("RAZAAI_KNOWLEDGE_DIR", str(PROJECT_ROOT / "knowledge"))).expanduser().resolve()
DATA_DIR = Path(os.getenv("RAZAAI_KNOWLEDGE_DATA_DIR", str(PROJECT_ROOT / "data"))).expanduser().resolve()
VECTORSTORE_DIR = DATA_DIR / "vectorstore"
MANIFEST_FILE = DATA_DIR / "knowledge_manifest.json"

COLLECTION_NAME = "razaai_ict_knowledge"
EMBEDDING_MODEL = "BAAI/bge-small-en"

CHUNK_SIZE = 1200
CHUNK_OVERLAP = 200
DEFAULT_TOP_K = 5

SUPPORTED_EXTENSIONS = {
    ".txt",
    ".md",
    ".markdown",
    ".pdf",
    ".html",
    ".htm",
}

DEFAULT_CATEGORIES = {
    "networking",
    "linux",
    "microsoft",
    "cybersecurity",
    "cloud",
    "virtualization",
    "servers",
    "programming",
    "vendors",
    "hardware",
    "school-infrastructure",
}
