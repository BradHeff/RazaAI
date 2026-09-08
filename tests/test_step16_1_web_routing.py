"""Deterministic web-routing tests."""

from app.agent.edge_router import EdgeIntentRouter


class FakeManager:
    def list_hosts(self):
        return []


class Interaction:
    mode = "conversation"


def main():
    print("=" * 56)
    print("RazaAI Step 16.1 Web Routing")
    print("=" * 56)

    router = EdgeIntentRouter(manager=FakeManager())

    route = router.route("can you use web yet?", interaction=Interaction())
    assert route.kind == "deterministic_response"
    assert "read-only public web" in route.response
    print("[PASS] web capability question does not browse")

    route = router.route(
        "search the web for Aruba CX 6100 documentation",
        interaction=Interaction(),
    )
    assert route.kind == "deterministic_tool"
    assert route.tool == "search_web"
    assert "Aruba CX 6100 documentation" in route.arguments["query"]
    print("[PASS] explicit web search routes deterministically")

    route = router.route(
        "what is the latest FortiOS release?",
        interaction=Interaction(),
    )
    assert route.kind == "deterministic_tool"
    assert route.tool == "search_web"
    print("[PASS] explicit freshness question routes to web")

    route = router.route(
        "read https://example.com/security-notes",
        interaction=Interaction(),
    )
    assert route.kind == "deterministic_tool"
    assert route.tool == "fetch_web_page"
    assert route.arguments["url"] == "https://example.com/security-notes"
    print("[PASS] explicit public URL retrieval routes deterministically")

    route = router.route(
        "why is site A unable to reach VLAN 20?",
        interaction=Interaction(),
    )
    assert route.kind == "model"
    print("[PASS] ordinary troubleshooting does not silently browse")

    route = router.route(
        "show me the current IP configuration",
        interaction=Interaction(),
    )
    # This is a local fact; it must be a deterministic local tool, never a web search.
    assert route.kind == "deterministic_tool" and route.tool == "get_ip_configuration"
    assert route.tool not in {"search_web", "fetch_web_page"}
    print("[PASS] local 'current' diagnostics run the local tool and are never mistaken for web freshness")

    print()
    print("=" * 56)
    print("STEP 16.1 WEB ROUTING PASSED")
    print("=" * 56)


if __name__ == "__main__":
    main()
