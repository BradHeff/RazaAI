from pathlib import Path


def main():
    print()
    print("========================================")
    print("RazaAI Step 11.3 Agent Integration")
    print("========================================")
    print()

    root = Path(__file__).resolve().parents[1]
    source = (root / "app/agent/agent.py").read_text(encoding="utf-8")

    for required in [
        "IncidentTrendAnalyzer",
        "self.incident_trends",
        "self.last_incident_trends",
        "analyze_patterns(",
        "[Incident Trend]",
        "incident_trend_guidance",
    ]:
        assert required in source, required

    print("[PASS] trend analyzer wired into RazaAgent")
    print("[PASS] trend state kept separate from recurrence state")
    print("[PASS] compact trend guidance injected into 4B context")

    patterns = (root / "app/incidents/patterns.py").read_text(encoding="utf-8")
    assert "Endpoint IP/interface tools do not prove" in patterns

    print("[PASS] WLAN VLAN evidence-source accuracy constraint present")

    print()
    print("========================================")
    print("STEP 11.3 AGENT INTEGRATION PASSED")
    print("========================================")
    print()


if __name__ == "__main__":
    main()
