"""Python-owned persistent memory tools."""

from __future__ import annotations

from app.memory import MemoryManager


def _manager():
    return MemoryManager()


def remember_memory(text, domain=None):
    record = _manager().remember_explicit(text, domain=domain)
    return {
        "status": "remembered",
        "memory": record.to_dict(),
    }


def search_memory(query="", domain=None, top_k=10):
    manager = _manager()

    if not str(query or "").strip():
        records = manager.summary(personal_only=True)[:max(0, int(top_k))]
        return {
            "query": "",
            "count": len(records),
            "memories": [record.to_dict() for record in records],
        }

    matches = manager.search(
        query,
        domain=domain,
        top_k=top_k,
        min_score=0.10,
    )
    return {
        "query": query,
        "count": len(matches),
        "memories": [
            {
                **record.to_dict(),
                "score": round(score, 4),
            }
            for score, record in matches
        ],
    }


def get_identity_profile(query=""):
    manager = _manager()
    return manager.identity_profile(query)

def memory_status():
    manager = _manager()
    all_records = manager.store.records(include_inactive=True)
    active = [record for record in all_records if record.state == "active"]
    review = [record for record in all_records if record.state == "review"]

    counts = {}
    for record in active:
        counts[record.kind] = counts.get(record.kind, 0) + 1

    return {
        "enabled": True,
        "store": str(manager.store.path),
        "active_count": len(active),
        "review_count": len(review),
        "counts_by_kind": counts,
        "learning": {
            "technical_observations": counts.get("technical_observation", 0),
            "technical_patterns": counts.get("technical_pattern", 0),
        },
    }


def forget_memory(query):
    forgotten = _manager().forget(query)
    return {
        "status": "forgotten",
        "count": len(forgotten),
        "memory_ids": [record.memory_id for record in forgotten],
    }


MEMORY_REMEMBER_METADATA = {
    "name": "remember_memory",
    "category": "memory",
    "risk": "persistent_local_write",
    "permission": "automatic",
    "timeout": 3,
    "model_exposed": False,
}
MEMORY_SEARCH_METADATA = {
    "name": "search_memory",
    "category": "memory",
    "risk": "local_read",
    "permission": "automatic",
    "timeout": 3,
    "model_exposed": False,
}
IDENTITY_PROFILE_METADATA = {
    "name": "get_identity_profile",
    "category": "memory",
    "risk": "local_read",
    "permission": "automatic",
    "timeout": 3,
    "model_exposed": False,
}
MEMORY_STATUS_METADATA = {
    "name": "memory_status",
    "category": "memory",
    "risk": "local_read",
    "permission": "automatic",
    "timeout": 3,
    "model_exposed": False,
}
MEMORY_FORGET_METADATA = {
    "name": "forget_memory",
    "category": "memory",
    "risk": "persistent_local_write",
    "permission": "automatic",
    "timeout": 3,
    "model_exposed": False,
}


def _def(name, description, properties, required=()):
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": list(required),
            },
        },
    }


MEMORY_REMEMBER_DEFINITION = _def(
    "remember_memory",
    "Persist a non-sensitive fact, preference or note explicitly requested by the user.",
    {
        "text": {"type": "string"},
        "domain": {"type": "string"},
    },
    ("text",),
)
MEMORY_SEARCH_DEFINITION = _def(
    "search_memory",
    "Read persistent RazaAI memory metadata and user-confirmed memories.",
    {
        "query": {"type": "string"},
        "domain": {"type": "string"},
        "top_k": {"type": "integer", "minimum": 1, "maximum": 20},
    },
)
IDENTITY_PROFILE_DEFINITION = _def(
    "get_identity_profile",
    "Return the user-confirmed persistent identity/profile facts for deterministic recall.",
    {"query": {"type": "string"}},
)
MEMORY_STATUS_DEFINITION = _def(
    "memory_status",
    "Return persistent memory status and counts.",
    {},
)
MEMORY_FORGET_DEFINITION = _def(
    "forget_memory",
    "Mark matching persistent memories forgotten.",
    {"query": {"type": "string"}},
    ("query",),
)
