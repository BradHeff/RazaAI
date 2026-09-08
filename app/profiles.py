"""Hardware defaults shared by the launchers, model setup and diagnostics."""

from dataclasses import dataclass

from .personality import MODEL_PERSONA


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

    def modelfile(self, source: str, *, coding: bool = False) -> str:
        """Build an Ollama model definition with this profile's memory limits."""
        if any(c in source for c in '\n\r'):
            raise ValueError('Model source must fit on one line')
        purpose = ('Propose code changes in the format requested by the application. '
                   'You cannot execute commands or write files. Never claim a test passed without supplied evidence.'
                   if coding else 'Answer clearly and concisely. Never invent tool results or observations.')
        return (f'FROM {source}\nPARAMETER num_ctx {self.context}\n'
                f'PARAMETER num_batch {self.batch}\nPARAMETER temperature {0.2 if coding else 0.6}\n'
                f'SYSTEM """{MODEL_PERSONA}\n{purpose}"""\n')


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
