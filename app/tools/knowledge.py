from app.knowledge import KnowledgeEngine


KNOWLEDGE_SEARCH_METADATA = {
    "name": "search_knowledge",
    "category": "knowledge",
    "risk": "read_only",
    "permission": "automatic",
    "timeout": 30,
}


def search_knowledge(
    query,
    top_k=5,
    category=None,
):
    engine = KnowledgeEngine()

    try:
        return {
            "query": query,
            "category": category,
            "results": engine.search(
                query=query,
                top_k=top_k,
                category=category,
            ),
        }
    finally:
        engine.close()


KNOWLEDGE_SEARCH_DEFINITION = {
    "type": "function",
    "function": {
        "name": "search_knowledge",
        "description": (
            "Search RazaAI's curated ICT knowledge base. The corpus includes "
            "vendor/reference documentation and operational field notes from "
            "real school ICT incidents. Prefer retrieved evidence for questions "
            "about recurring school infrastructure faults, networking, Microsoft "
            "365, Intune, Active Directory, servers, Linux and filtering systems. "
            "Treat field notes as environment-specific experience rather than "
            "universal vendor documentation."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Technical question or semantic search phrase.",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Number of relevant chunks to retrieve.",
                    "default": 5,
                },
                "category": {
                    "type": "string",
                    "description": (
                        "Optional category filter: networking, linux, microsoft, "
                        "servers, cybersecurity, cloud, virtualization, programming, "
                        "vendors, hardware or school-infrastructure."
                    ),
                },
            },
            "required": ["query"],
        },
    },
}
