from pathlib import Path


def main():
    print()
    print("========================================")
    print("RazaAI Step 11.1 Agent Integration Test")
    print("========================================")
    print()

    root = Path(__file__).resolve().parents[1]
    source = (root / "app" / "agent" / "agent.py").read_text()
    engine = (root / "app" / "diagnostics" / "engine.py").read_text()

    required_agent = [
        "IncidentRetriever",
        "self.incident_retriever = IncidentRetriever",
        "self.last_incident_matches = self.incident_retriever.search",
        "[Incident Memory] Retrieved:",

        "incident_memory_guidance = (",
        "self.incident_retriever.guidance(self.last_incident_matches)",
    ]

    for value in required_agent:
        if value not in source:
            raise AssertionError(f"Missing agent integration: {value}")

    print("[PASS] incident retrieval wired into RazaAgent")

    if "prior_incidents:" not in engine:
        raise AssertionError("DiagnosticContext lacks prior incident state")

    print("[PASS] DiagnosticContext can retain prior incidents")

    if "top_k=2" not in source:
        raise AssertionError("Edge context is not capped to two prior incidents")

    print("[PASS] edge model retrieval capped to top two incidents")

    print()
    print("========================================")
    print("STEP 11.1 AGENT INTEGRATION PASSED")
    print("========================================")
    print()


if __name__ == "__main__":
    main()
