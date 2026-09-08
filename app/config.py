import os
from pathlib import Path

# RazaAI project root
BASE_DIR = Path(__file__).resolve().parent.parent

from .profiles import get_profile

PROFILE = get_profile(os.getenv("RAZAAI_PROFILE", "standard"))
OLLAMA_HOST = os.getenv("RAZAAI_OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("RAZAAI_OLLAMA_MODEL", "").strip() or PROFILE.model
APPROVED_CODE_MODEL = PROFILE.code_model
APPROVED_CODE_QUANTIZATION = "Q4_K_M" if PROFILE.name == "8g" else None
CODE_MODEL = os.getenv("RAZAAI_CODE_MODEL", "").strip() or APPROVED_CODE_MODEL
CODE_MODEL_OVERRIDE_REJECTED = False


def positive_int(name: str, default: int) -> int:
    """Read a positive integer setting and identify invalid configuration."""
    raw = os.getenv(name, "").strip()
    try:
        value = int(raw) if raw else default
    except ValueError:
        raise ValueError(f"{name} must be a positive integer") from None
    if value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


OLLAMA_NUM_CTX = positive_int("RAZAAI_OLLAMA_NUM_CTX", PROFILE.context)
OLLAMA_NUM_BATCH = positive_int("RAZAAI_OLLAMA_NUM_BATCH", PROFILE.batch)
if PROFILE.name == "8g" and (OLLAMA_NUM_CTX > PROFILE.context or OLLAMA_NUM_BATCH > PROFILE.batch):
    raise ValueError("The 8g profile supports at most 4096 context tokens and a 128-token batch")
OLLAMA_KEEP_ALIVE = os.getenv("RAZAAI_OLLAMA_KEEP_ALIVE", "5m").strip() or "5m"
_raw_window = os.getenv("RAZAAI_OLLAMA_CONTEXT_WINDOW", "").strip()
OLLAMA_CONTEXT_WINDOW_OVERRIDE = (
    positive_int("RAZAAI_OLLAMA_CONTEXT_WINDOW", OLLAMA_NUM_CTX) if _raw_window else None
)
if OLLAMA_CONTEXT_WINDOW_OVERRIDE and OLLAMA_CONTEXT_WINDOW_OVERRIDE > OLLAMA_NUM_CTX:
    raise ValueError("RAZAAI_OLLAMA_CONTEXT_WINDOW cannot exceed RAZAAI_OLLAMA_NUM_CTX")
OLLAMA_CONTEXT_WINDOW_FALLBACK = OLLAMA_NUM_CTX
OLLAMA_CONTEXT_WINDOW = OLLAMA_CONTEXT_WINDOW_OVERRIDE or OLLAMA_NUM_CTX
OLLAMA_OUTPUT_RESERVE = positive_int("RAZAAI_OLLAMA_OUTPUT_RESERVE", 700)
if OLLAMA_OUTPUT_RESERVE >= OLLAMA_CONTEXT_WINDOW:
    raise ValueError("RAZAAI_OLLAMA_OUTPUT_RESERVE must be smaller than the context window")

# Self-modification authority (self-patching, self-improvement
# promotion, model training, active-model replacement). Off by default so an
# unattended edge device cannot rewrite its own source or swap its model.
# Enable deliberately on a workstation with RAZAAI_SELFOPS=1.
SELFOPS_ENABLED = os.getenv("RAZAAI_SELFOPS", "0").strip().casefold() in {
    "1",
    "true",
    "yes",
    "on",
}

# Tool risk classes that count as self-modification.
SELF_MODIFYING_RISKS = frozenset(
    {
        "source_write",
        "sandbox_write",
        "sandbox_execution",
        "dataset_write",
        "gpu_training",
        "candidate_runtime",
        "active_model_replace",
    }
)

# Identity/origin facts are Python authority. Persistent memory must
# never override them (a user saying "remember X made you" is not evidence).
IDENTITY_FACTS = {
    "name": "RazaAI",
    "creator": "Brad Heffernan",
    "model": "Qwen3 4B Heretic Q4_K_M",
    "runtime": "Ollama",
    "origin_year": 2019,
    "origin": "built by Brad Heffernan in 2019 as a simple chatbot using movie scripts as source material and keyword detection for funny responses",
    "resumed_year": 2024,
    "resumed": "serious development resumed in 2024 as modern AI tools and proper LLMs became widely available",
}
# Brad's other products are Python authority too :  without this the
# model treats VigilGLM as unconfirmed and denies it exists.
PRODUCT_FACTS = {
    "vigilglm": {
        "name": "VigilGLM",
        "url": "https://vigilglm.ai",
        "summary": "Brad Heffernan's cloud AI chat platform — the cloud sibling of RazaAI",
        "assistant": "SIERRA",
        "model": "GLM-5.3",
        # Pricing is volatile: serve from knowledge/project/vigilglm-ai.md, never hardcode.
    },
}
# Underlying lineage per Ollama tag prefix; the identity anchor must describe
# whichever model is actually answering.
MODEL_LINEAGE = {
    "razaai-8g": "Qwen3 4B Q4_K_M",
    "razaai-coder": "Qwen2.5-Coder 7B Instruct Q4_K_M",
    "razaai": "GLM-4 9B",
    "raza-edge": "Qwen3 4B Heretic Q4_K_M",
    "raza-glm": "GLM-4 9B 0414 Q4_K_M",
    "raza-coder:qwen3-4b": "Qwen3 4B Instruct 2507 Q4_K_M",
    "raza-coder:3b-v1": "Qwen2.5-Coder 3B Q4_K_M",
    "raza-coder:3b": "Qwen2.5-Coder 3B Q4_K_M",
}


def model_lineage(tag: str | None) -> str:
    tag = str(tag or "")
    for prefix, lineage in sorted(MODEL_LINEAGE.items(), key=lambda kv: -len(kv[0])):
        if tag.startswith(prefix):
            return lineage
    return tag or IDENTITY_FACTS["model"]

# The identity anchor must describe the session's actual model. With
# a static value, running raza-glm made Python authority claim the Qwen base.
IDENTITY_FACTS["model"] = model_lineage(OLLAMA_MODEL)


from .personality import RAZAAI_VOICE_CONTRACT


IDENTITY_ORIGIN_STORY = (
    "RazaAI began in 2019, when Brad Heffernan built a simple chatbot using movie scripts as source "
    "material and keyword detection for funny responses. Serious development resumed in "
    "2024 as modern AI tools and proper LLMs became widely available, and RazaAI grew into "
    "the evidence-first technical assistant it is today."
)


# Mutable runtime state (memory, incidents, feedback, promotions,
# audits). Read at call time so an evaluation can point every store at a fresh
# temporary directory and stay hermetic. Knowledge/vector data stays under
# BASE_DIR/data :  it is read-only for evaluations.
def state_dir() -> Path:
    raw = os.getenv("RAZAAI_STATE_DIR", "").strip()
    return Path(raw).expanduser().resolve() if raw else (BASE_DIR / "data")


# Application
APP_NAME = "RazaAI"
APP_VERSION = "20.16.0"


def version_tuple(value=None):
    """Parse 'MAJOR.MINOR.PATCH' into a comparable tuple."""
    parts = []
    for piece in str(value or APP_VERSION).split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        parts.append(int(digits or 0))
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


APP_VERSION_TUPLE = version_tuple(APP_VERSION)

# Logging
LOG_DIR = BASE_DIR / "logs"
LOG_FILE = LOG_DIR / "razaai.log"
