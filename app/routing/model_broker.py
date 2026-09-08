"""Model broker."""
from ..config import OLLAMA_MODEL, CODE_MODEL

class ModelBroker:
    def model_for(self, task: str):
        if task == "coding":
            return CODE_MODEL
        return OLLAMA_MODEL
