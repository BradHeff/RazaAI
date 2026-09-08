"""RazaAI:  application-server and VPN symptom prompts route to the right expert, trigger evidence retrieval, and find curated knowledge (offline)."""

from pathlib import Path

from app.diagnostics.engine import DiagnosticEngine
from app.experts.router import ExpertRouter
from app.tools.registry import ToolRegistry

NGINX = "Nginx returns 502 Bad Gateway for a local application. What should I verify first?"
IPSEC = ("A FortiGate IPsec tunnel is down. Give me a systematic troubleshooting "
         "order without changing configuration.")


def main():
    print("=" * 78)
    print("RazaAI Step 20.8.8 Advice Evidence Routing")
    print("=" * 78)

    router = ExpertRouter()
    assert router.route(NGINX).expert == "servers", router.route(NGINX)
    assert router.route(IPSEC).expert == "networking"
    assert router.route("What is the default gateway on this machine?").expert == "networking"
    assert router.route("the site B gateway is unreachable").expert == "networking"
    print("[PASS] 'Bad Gateway' is an application-server symptom; plain 'gateway' stays networking")

    diag = DiagnosticEngine()
    assert diag.is_troubleshooting(NGINX)
    assert diag.is_troubleshooting(IPSEC)
    assert diag.is_troubleshooting("apache returns 503 for every request")
    assert not diag.is_troubleshooting("What is the default gateway on this machine?")
    assert not diag.is_troubleshooting("explain how nginx reverse proxying works")
    print("[PASS] HTTP 5xx / tunnel-down / verify-first phrasing triggers evidence retrieval")

    for rel in ("knowledge/servers/nginx-502-bad-gateway-troubleshooting.md",
                "knowledge/networking/fortigate-ipsec-tunnel-down-troubleshooting.md"):
        assert Path(rel).is_file() and Path(rel + ".meta.json").is_file(), rel
    nginx_doc = Path("knowledge/servers/nginx-502-bad-gateway-troubleshooting.md").read_text(encoding="utf-8").lower()
    ipsec_doc = Path("knowledge/networking/fortigate-ipsec-tunnel-down-troubleshooting.md").read_text(encoding="utf-8").lower()
    assert all(term in nginx_doc for term in ("upstream", "socket", "listen", "error.log"))
    assert all(term in ipsec_doc for term in ("phase 1", "phase 2", "selectors", "route", "policy"))
    print("[PASS] curated nginx-502 and FortiGate-IPsec knowledge documents exist with the expected coverage")

    registry = ToolRegistry()
    for query, category, filename in (
        (NGINX, "servers", "nginx-502-bad-gateway-troubleshooting.md"),
        (IPSEC, "networking", "fortigate-ipsec-tunnel-down-troubleshooting.md"),
    ):
        result = registry.execute("search_knowledge", {"query": query, "category": category})
        assert result.success, result.error
        top = result.result["results"][0]["citation"]["filename"]
        assert top == filename, (query[:30], top)
    print("[PASS] the new documents are the top ranked evidence for both capability prompts")

    print("=" * 78)
    print("STEP 20.8.8 ADVICE EVIDENCE ROUTING PASSED")
    print("=" * 78)


if __name__ == "__main__":
    main()
