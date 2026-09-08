"""Hardware defaults shared by the launchers, model setup and diagnostics."""

from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeProfile:
    name: str
    model: str
    code_model: str
    context: int
    batch: int
    sessions: int
    port: int
    base_model: str
    code_base: str


PROFILES = {
    "standard": RuntimeProfile(
        "standard", "razaai", "razaai-coder", 16384, 512, 4, 8420,
        "glm4:9b", "qwen2.5-coder:7b-instruct-q4_K_M",
    ),
    "8g": RuntimeProfile(
        "8g", "razaai-8g", "razaai-8g-coder", 4096, 128, 2, 8421,
        "hf.co/unsloth/Qwen3-4B-Instruct-2507-GGUF:Q4_K_M",
        "hf.co/unsloth/Qwen3-4B-Instruct-2507-GGUF:Q4_K_M",
    ),
}


def get_profile(name: str) -> RuntimeProfile:
    try:
        return PROFILES[name]
    except KeyError:
        raise ValueError("RAZAAI_PROFILE must be 'standard' or '8g'") from None
