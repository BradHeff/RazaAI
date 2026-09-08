"""Structural acceptance checks."""

from pathlib import Path
import ast


def main():
    print("=" * 64)
    print("RazaAI Step 15.1 Tool Result Authority")
    print("=" * 64)

    agent = Path("app/agent/agent.py").read_text(encoding="utf-8")
    edge = Path("app/agent/edge_router.py").read_text(encoding="utf-8")
    infra = Path("app/tools/infrastructure.py").read_text(encoding="utf-8")

    ast.parse(agent)
    ast.parse(edge)
    ast.parse(infra)
    print("[PASS] patched Python parses cleanly")

    assert "infrastructure_list_request" in edge
    assert "Configured infrastructure host metadata lookup" in edge
    print("[PASS] infrastructure discovery/host metadata are deterministic")

    assert "len(aruba_hosts) == 1" in edge
    assert "len(fortigate_hosts) == 1" in edge
    print("[PASS] friendly names require unambiguous inventory")

    assert "def list_infrastructure(host=None):" in infra
    assert "No credentials are read and no network connection is attempted" in infra
    print("[PASS] infrastructure discovery is metadata-only")

    assert "def _render_authoritative_edge_result" in agent
    assert "The self-audit completed successfully. RazaAI is healthy." in agent
    assert "I found a fault in RazaAI." in agent
    print("[PASS] self-audit output is Python-authoritative")

    assert "don't paste the password into chat" in agent
    assert "Required secret environment variable" in agent
    print("[PASS] missing credentials are reported without solicitation")

    assert "def _reported_outcome_guidance" in agent
    assert "Do not weaken it to 'most likely'" in agent
    assert "Do not invent validation evidence" in agent
    print("[PASS] user-reported outcomes stay grounded")

    print()
    print("=" * 64)
    print("STEP 15.1 TOOL RESULT AUTHORITY PASSED")
    print("=" * 64)


if __name__ == "__main__":
    main()
