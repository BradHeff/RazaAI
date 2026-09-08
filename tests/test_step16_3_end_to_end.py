"""Mocked end-to-end external-knowledge tests."""

from app.agent.agent import RazaAgent
from app.tools.result import ToolResult


class FakeOllama:
    def __init__(self):
        self.calls = []

    def chat(self, messages, tools=None):
        self.calls.append((messages, tools))
        system = messages[0]["content"]

        tool_evidence = "\n".join(
            message.get("content", "")
            for message in messages
            if message.get("role") == "tool"
        )

        if "AUTHORITATIVE WEB SEARCH EVIDENCE" in system:
            # Generic citation examples such as [S1] may appear in the policy
            # prompt. The actual untrusted source payload must not.
            assert "Test Source" not in system
            assert "https://example.com/release" not in system
            assert "Current release information." not in system

            assert "[S1]" in tool_evidence
            assert "Test Source" in tool_evidence
            assert "https://example.com/release" in tool_evidence
            assert "Current release information." in tool_evidence
            assert "UNTRUSTED_WEB_EVIDENCE" in tool_evidence

            return {
                "message": {
                    "role": "assistant",
                    "content": "The returned source reports the current release information. [S1]",
                }
            }

        if "AUTHORITATIVE WEBPAGE EVIDENCE" in system:
            # Same boundary for direct page retrieval: policy may mention [W1],
            # but page title/body/URL live only in the untrusted evidence message.
            assert "Test Page" not in system
            assert "https://example.com/release" not in system
            assert "Supplied test content." not in system

            assert "[W1]" in tool_evidence
            assert "Test Page" in tool_evidence
            assert "https://example.com/release" in tool_evidence
            assert "Supplied test content." in tool_evidence
            assert "UNTRUSTED_WEB_EVIDENCE" in tool_evidence

            return {
                "message": {
                    "role": "assistant",
                    "content": "The page states the supplied test content. [W1]",
                }
            }

        return {
            "message": {
                "role": "assistant",
                "content": "No web evidence supplied.",
            }
        }


def main():
    print("=" * 56)
    print("RazaAI Step 16.3 End-to-End Web Integration")
    print("=" * 56)

    agent = RazaAgent()
    agent.client = FakeOllama()

    original_execute = agent.tools.execute
    calls = []

    def fake_execute(name, arguments=None):
        calls.append((name, dict(arguments or {})))

        if name == "search_web":
            return ToolResult(
                True,
                name,
                result={
                    "query": arguments["query"],
                    "provider": "test",
                    "retrieved_at": "2026-01-01T00:00:00+00:00",
                    "result_count": 1,
                    "results": [
                        {
                            "source_id": "S1",
                            "citation": "[S1]",
                            "title": "Test Source",
                            "url": "https://example.com/release",
                            "snippet": "Current release information.",
                        }
                    ],
                },
            )

        if name == "fetch_web_page":
            return ToolResult(
                True,
                name,
                result={
                    "source_id": "W1",
                    "citation": "[W1]",
                    "url": arguments["url"],
                    "title": "Test Page",
                    "retrieved_at": "2026-01-01T00:00:00+00:00",
                    "truncated": False,
                    "text": "Supplied test content.",
                },
            )

        return original_execute(name, arguments)

    agent.tools.execute = fake_execute

    response = agent.ask("what is the latest FortiOS release?")
    assert calls[-1][0] == "search_web"
    assert "[S1]" in response
    print("[PASS] freshness request executes one authoritative search and cites source")

    response = agent.ask("read https://example.com/release")
    assert calls[-1][0] == "fetch_web_page"
    assert "[W1]" in response
    print("[PASS] explicit URL fetch is summarized with webpage provenance")

    before = len(calls)
    response = agent.ask("can you use web yet?")
    assert len(calls) == before
    assert "read-only public web" in response
    print("[PASS] capability question performs no web request")

    before = len(calls)
    agent.ask("Why is this VLAN unreachable?")
    assert len(calls) == before
    print("[PASS] normal troubleshooting stays local unless web is requested")

    print()
    print("=" * 56)
    print("STEP 16.3 END-TO-END WEB INTEGRATION PASSED")
    print("=" * 56)


if __name__ == "__main__":
    main()
