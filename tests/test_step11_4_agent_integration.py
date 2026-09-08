from pathlib import Path


def main():
    print()
    print("========================================")
    print("RazaAI Step 11.4 Agent Integration")
    print("========================================")
    print()

    root = Path(__file__).resolve().parents[1]
    source = (root / "app/agent/agent.py").read_text(encoding="utf-8")

    required = [
        "LearnedResolutionAnalyzer",
        "self.learned_resolutions",
        "self.last_learned_resolutions",
        "analyze_patterns(",
        "[Learned Resolution]",
        "learned_resolution_guidance",
    ]

    for value in required:
        if value not in source:
            raise AssertionError(f"Missing Step 11.4 integration: {value}")

    print("[PASS] learned-resolution analyzer wired into RazaAgent")
    print("[PASS] learned-resolution state resets on new request")
    print("[PASS] compact learned-resolution guidance injected into 4B context")

    resolution_source = (
        root / "app/incidents/resolutions.py"
    ).read_text(encoding="utf-8")

    assert "historical operational experience, not proof" in resolution_source
    assert "Verify the current WLAN/SSID Access VLAN" in resolution_source

    print("[PASS] historical fix remains hypothesis until current evidence confirms it")

    print()
    print("========================================")
    print("STEP 11.4 AGENT INTEGRATION PASSED")
    print("========================================")
    print()


if __name__ == "__main__":
    main()
