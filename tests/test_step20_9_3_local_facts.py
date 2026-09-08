"""RazaAI:  read-only facts about this machine are deterministic tool routes."""

from unittest.mock import patch

from app.agent.edge_router import local_fact_route
from app.tools.routing import get_routing_table


class _NeverModel:
    num_ctx = None
    last_usage = {}

    def detect_context_window(self, fallback=None, timeout=5):
        return 8192

    def chat(self, messages, tools=None):
        raise AssertionError("the model must not be consulted for a local fact")

    chat_stream = chat


def main():
    print("=" * 78)
    print("RazaAI Step 20.9.3 Local Facts")
    print("=" * 78)

    cases = {
        "what is the default gateway on this machine?": "get_ip_configuration",
        "what's my IP address?": "get_ip_configuration",
        "What IP configuration does this machine have right now?": "get_ip_configuration",
        "what dns servers are you using?": "get_ip_configuration",
        "show me the routing table": "get_routing_table",
        "check the default gateway": "get_ip_configuration",
        "what interfaces does this box have?": "get_network_interfaces",
        "what's your hostname?": "get_system_info",
    }
    for q, tool in cases.items():
        assert local_fact_route(q.lower()) == tool, (q, local_fact_route(q.lower()))
    print("[PASS] gateway / IP / DNS / routes / interfaces / host facts route to the read-only local tool")

    for q in ("what is a default gateway?", "explain how routing works",
              "what is the default gateway of the fortigate at site B?",
              "what's the default gateway on 192.168.1.10?",
              "how do I fix a wrong default gateway on a client?",
              "is this switch port actually down?"):
        assert local_fact_route(q.lower()) is None, q
    print("[PASS] conceptual questions and remote targets are not local facts")

    with patch("app.agent.agent.OllamaClient", _NeverModel):
        from app.agent import RazaAgent
        agent = RazaAgent()
        answer = agent.ask("what is the default gateway on this machine?")
        assert "Default gateway:" in answer and "DNS servers:" in answer
        table = agent.ask("show me the routing table")
        assert table.startswith("Routing table on this machine:")
    print("[PASS] the agent answers local facts from tool evidence without consulting the model")

    result = get_routing_table()
    assert set(result) == {"ipv4", "ipv6"} and all("success" in v for v in result.values())
    print("[PASS] get_routing_table reports an unavailable `ip` binary instead of raising")

    print("=" * 78)
    print("STEP 20.9.3 LOCAL FACTS PASSED")
    print("=" * 78)


if __name__ == "__main__":
    main()
