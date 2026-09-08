"""Conversational coding intent bridge."""
import re

_MUTATION = re.compile(r"\b(edit|modify|change|fix|update|refactor|add|remove|replace|rewrite|patch|create|reate|write)\b", re.I)
_FILE = re.compile(r"\b[\w./-]+\.(py|js|ts|json|yaml|yml|md|conf|cfg|sh)\b", re.I)


def is_coding_modification_request(text: str) -> bool:
    """Detect requested workspace mutations, not coding questions."""
    if not text:
        return False
    return bool(_MUTATION.search(text) and _FILE.search(text))
