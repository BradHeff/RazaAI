"""RazaAI:  origin facts (2019 chatbot, 2024 resumed) are Python identity authority."""

from pathlib import Path
from unittest.mock import patch

from app.config import IDENTITY_FACTS, IDENTITY_ORIGIN_STORY
from app.agent.agent import RAZAAI_CORE_IDENTITY, _is_self_identity_topic


class _Capture:
    num_ctx = None
    last_usage = {}

    def __init__(self):
        self.system = ""

    def detect_context_window(self, fallback=None, timeout=5):
        return 8192

    def chat(self, messages, tools=None):
        self.system = "\n".join(m["content"] for m in messages if m["role"] == "system")
        return {"message": {"content": "2019."}}

    def chat_stream(self, messages, tools=None, on_chunk=None):
        return self.chat(messages, tools)


def main():
    print("=" * 78)
    print("RazaAI Step 20.8.10 Identity Origin Authority")
    print("=" * 78)

    assert IDENTITY_FACTS["origin_year"] == 2019 and IDENTITY_FACTS["resumed_year"] == 2024
    assert "movie scripts" in IDENTITY_ORIGIN_STORY and "2024" in IDENTITY_ORIGIN_STORY
    assert "2019" in RAZAAI_CORE_IDENTITY and "Brad Heffernan created RazaAI." in RAZAAI_CORE_IDENTITY
    print("[PASS] origin facts live in config and the core identity anchor")

    for q in ("when were you created?", "how old are you?", "what's your history?",
              "when did you start?", "who made you?"):
        assert _is_self_identity_topic(q), q
    assert not _is_self_identity_topic("when did the tunnel go down?")
    print("[PASS] 'when created / how old / history' are identity turns; unrelated 'when' is not")

    client = _Capture()
    with patch("app.agent.agent.OllamaClient", lambda: client):
        from app.agent import RazaAgent
        agent = RazaAgent()
        r1 = agent.ask("who made you?")
        r2 = agent.ask("when?")                       # Identity follow-up stays authoritative
    # identity turns (including follow-ups) are answered by the
    # Python authority layer; the model is not consulted. Both milestones
    # must appear in the authoritative answers themselves.
    assert "2019" in r1 or "2019" in r2
    assert "2019" in r2 and "2024" in r2, r2
    from app.conversation_coherence import self_identity_authoritative_response
    anchor = self_identity_authoritative_response("when", identity_context_active=True)
    assert "2019" in anchor and "2024" in anchor
    print("[PASS] identity follow-ups answer created/resumed years from Python authority (model never consulted)")

    modelfile = Path("Modelfile.raza-edge-v3").read_text(encoding="utf-8")
    assert "2019" in modelfile and "movie scripts" in modelfile and "2024" in modelfile
    print("[PASS] Modelfile SYSTEM carries the origin story (re-run `ollama create` to apply)")

    seed = Path("training/identity_origin_v4_seed.jsonl")
    lines = [l for l in seed.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) >= 10
    assert all("2019" in l for l in lines)

    print("[PASS] reviewed identity seed contains the origin facts")

    print("=" * 78)
    print("STEP 20.8.10 IDENTITY ORIGIN AUTHORITY PASSED")
    print("=" * 78)


if __name__ == "__main__":
    main()
