"""RazaAI deterministic memory routing."""

from app.agent.edge_router import EdgeIntentRouter


class FakeManager:
    def list_hosts(self):
        return []


class Interaction:
    mode = "conversation"
    domain = "general"


def main():
    print("=" * 64)
    print("RazaAI Step 17.2 Memory Routing")
    print("=" * 64)

    router = EdgeIntentRouter(manager=FakeManager())

    route = router.route(
        "can you learn and remember things?",
        interaction=Interaction(),
    )
    assert route.kind == "deterministic_response"
    assert "persistent local memory" in route.response
    print("[PASS] memory capability question is answered without model tooling")

    route = router.route(
        "remember that my editor is vim",
        interaction=Interaction(),
    )
    assert route.kind == "deterministic_tool"
    assert route.tool == "remember_memory"
    assert route.arguments["text"] == "my editor is vim"
    print("[PASS] explicit remember request is Python-routed")

    route = router.route(
        "what do you remember about me?",
        interaction=Interaction(),
    )
    assert route.kind == "deterministic_tool"
    assert route.tool == "search_memory"
    print("[PASS] memory summary request is Python-routed")

    route = router.route(
        "what is my name?",
        interaction=Interaction(),
    )
    assert route.kind == "deterministic_tool"
    assert route.tool == "search_memory"
    print("[PASS] direct recall request is Python-routed")

    route = router.route(
        "forget my editor",
        interaction=Interaction(),
    )
    assert route.kind == "deterministic_tool"
    assert route.tool == "forget_memory"
    print("[PASS] forget request is Python-routed")

    print()
    print("=" * 64)
    print("STEP 17.2 MEMORY ROUTING PASSED")
    print("=" * 64)


if __name__ == "__main__":
    main()
