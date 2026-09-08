"""RazaAI Qwen context safety hotfix."""

import io
import json
import urllib.error
from pathlib import Path

from app.context_budget import compact_messages, estimate_messages
from app.ollama_client import _ollama_http_error


def main():
    print("=" * 74)
    print("RazaAI Step 20.4.1 Context Safety Hotfix")
    print("=" * 74)

    messages = [
        {"role": "system", "content": "SYSTEM CONTRACT\\n" + ("networking evidence rules; " * 700)},
    ]
    for i in range(10):
        messages += [
            {"role": "user", "content": f"historic user {i} " + ("x" * 350)},
            {"role": "assistant", "content": f"historic assistant {i} " + ("y" * 350)},
        ]
    messages += [
        {"role": "tool", "content": "CURRENT MEMORY EVIDENCE\\n" + ("fact " * 200)},
        {
            "role": "user",
            "content": (
                "what if i want to check 1 way audio on NEC phone for internal "
                "calls between campus over ipsec VPN tunnel?"
            ),
        },
    ]

    compacted, report = compact_messages(
        messages,
        context_window=4096,
        reserve_output_tokens=700,
    )
    assert report["fits_estimate"]
    assert compacted[-1]["content"].startswith("what if i want to check")
    assert any("CURRENT MEMORY EVIDENCE" in str(m.get("content")) for m in compacted)
    assert not any("historic user 0" in str(m.get("content")) for m in compacted)
    print("[PASS] conservative Qwen budget preserves current request/evidence")

    body = json.dumps({
        "error": json.dumps({
            "error": {
                "code": 400,
                "message": (
                    "request (4769 tokens) exceeds the available context size "
                    "(4096 tokens), try increasing it"
                ),
                "type": "exceed_context_size_error",
                "n_prompt_tokens": 4769,
                "n_ctx": 4096,
            }
        })
    }).encode("utf-8")

    exc = urllib.error.HTTPError(
        "http://127.0.0.1:11434/api/chat",
        400,
        "Bad Request",
        {},
        io.BytesIO(body),
    )
    parsed = _ollama_http_error(exc)
    assert parsed.context_exceeded is True
    assert parsed.n_prompt_tokens == 4769
    assert parsed.n_ctx == 4096
    print("[PASS] nested Ollama context overflow yields real prompt/context counts")

    # The agent tightens the chars/token estimate from Ollama's real
    # count before the emergency pass, exactly as the live retry path does.
    import app.context_budget as budget
    saved_estimate = budget.ESTIMATED_CHARS_PER_TOKEN
    budget.tighten_estimate(parsed.n_prompt_tokens, estimate_messages(compacted))
    assert budget.ESTIMATED_CHARS_PER_TOKEN < saved_estimate
    emergency, emergency_report = compact_messages(
        compacted,
        context_window=parsed.n_ctx,
        reserve_output_tokens=900,
        safety_tokens=384,
        aggressive=True,
    )
    budget.ESTIMATED_CHARS_PER_TOKEN = saved_estimate
    assert emergency_report["aggressive"] is True
    assert emergency_report["fits_estimate"] is True
    assert emergency[-1]["content"] == compacted[-1]["content"]
    assert estimate_messages(emergency) < estimate_messages(compacted)
    print("[PASS] emergency compaction preserves current question and shrinks request")

    agent = Path("app/agent/agent.py").read_text(encoding="utf-8")
    assert "except OllamaError as exc" in agent
    assert "exc.context_exceeded" in agent
    assert "aggressive=True" in agent
    assert "retrying once" in agent
    print("[PASS] agent automatically retries exactly one context-overflow request")

    print()
    print("=" * 74)
    print("STEP 20.4.1 CONTEXT SAFETY HOTFIX PASSED")
    print("=" * 74)


if __name__ == "__main__":
    main()
