"""RazaAI:  hidden thinking, streamed answer."""

from app.ollama_client import OllamaClient


class _FakeResponse:
    def __init__(self, events):
        self._events = events

    def __iter__(self):
        import json

        for event in self._events:
            yield (json.dumps(event) + "\n").encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _client_with_stream(events):
    client = OllamaClient.__new__(OllamaClient)
    client.host = "http://fake"
    client.model = "m"
    client.keep_alive = "30m"
    client.num_ctx = None
    client.last_usage = {"prompt_tokens": None, "output_tokens": None, "context_window": 8192}
    client.last_thinking = ""
    OllamaClient._capabilities_cache[("http://fake", "m")] = set()

    import urllib.request

    def fake_urlopen(request, timeout=None):
        return _FakeResponse(events)

    urllib.request.urlopen = fake_urlopen
    return client


def main():
    print("=" * 78)
    print("RazaAI Step 20.15.2 Hidden Thinking Stream")
    print("=" * 78)

    done = {"done": True, "prompt_tokens": 10, "eval_tokens": 5}


    events = [
        {"message": {"content": "<thi"}},
        {"message": {"content": "nk>the VLAN is wrong</th"}},
        {"message": {"content": "ink>Change the WLAN Access VLAN to 80, then reconnect the client."}},
        done,
    ]
    client = _client_with_stream(events)
    body, thinking = [], []
    result = client.chat_stream([], on_chunk=body.append, on_thinking=thinking.append)
    assert "".join(body) == "Change the WLAN Access VLAN to 80, then reconnect the client.", body
    assert "the VLAN is wrong" in "".join(thinking)
    assert "<think>" not in result["message"]["content"]
    assert "VLAN is wrong" in client.last_thinking
    print("[PASS] inline <think> split across chunks: reasoning to on_thinking, clean body to on_chunk")


    events = [
        {"message": {"thinking": "considering the DHCP scope ", "content": ""}},
        {"message": {"thinking": "and the relay address", "content": "Check the DHCP relay on VLAN 30."}},
        done,
    ]
    client = _client_with_stream(events)
    body, thinking = [], []
    client.chat_stream([], on_chunk=body.append, on_thinking=thinking.append)
    assert "".join(body) == "Check the DHCP relay on VLAN 30.", body
    assert "DHCP scope" in "".join(thinking) and "relay address" in "".join(thinking)
    print("[PASS] native message.thinking streams to on_thinking, never the body")


    events = [
        {"message": {"content": "Simple answer."}},
        done,
    ]
    client = _client_with_stream(events)
    body, thinking = [], []
    result = client.chat_stream([], on_chunk=body.append, on_thinking=thinking.append)
    assert "".join(body) == "Simple answer." and thinking == []
    assert client.last_thinking == ""
    print("[PASS] ordinary streams unchanged")

    # 4. Unterminated think block (stream cut mid-reasoning): nothing leaks.
    events = [
        {"message": {"content": "<think>half a thought, stream d"}},
        done,
    ]
    client = _client_with_stream(events)
    body, thinking = [], []
    result = client.chat_stream([], on_chunk=body.append, on_thinking=thinking.append)
    assert body == [], body
    assert result["message"]["content"] == ""
    assert "half a thought" in "".join(thinking)
    print("[PASS] unterminated think block never leaks into the answer")

    # 5. Unit-level: marker-partial holdback across many split points.
    for cut in range(1, 7):
        text = "<think>abc</think>xyz"
        state = ["outside"]
        pending = [""]
        out = {"body": "", "think": ""}
        for i in range(0, len(text), cut):
            for kind, piece in OllamaClient._split_think_stream(state, pending, text[i:i + cut]):
                out[kind] += piece
        # Any marker tail still buffered at end-of-stream is dropped by the
        # caller only when the stream ends; a well-formed stream resolves it.
        assert out["think"].startswith("abc") and "xyz" in out["body"], (cut, out)
    print("[PASS] split filter is correct at every chunk boundary")


    import json as _json

    class _FakeResp2(_FakeResponse):
        def read(self):
            return _json.dumps({
                "message": {"thinking": "reasoned deeply", "content": "The answer."},
                "done": True,
            }).encode("utf-8")

    import urllib.request

    urllib.request.urlopen = lambda request, timeout=None: _FakeResp2([])
    client2 = OllamaClient.__new__(OllamaClient)
    client2.host = "http://fake"
    client2.model = "m"
    client2.keep_alive = "30m"
    client2.num_ctx = None
    client2.last_usage = {"prompt_tokens": None, "output_tokens": None, "context_window": 8192}
    client2.last_thinking = ""
    OllamaClient._capabilities_cache[("http://fake", "m")] = set()
    result = client2.chat([])
    assert result["message"]["content"] == "The answer."
    assert client2.last_thinking == "reasoned deeply"
    print("[PASS] non-streaming chat() keeps reasoning for diagnostics, strips it from the answer")

    # 7. TUI indicator contract: thinking counter, not thinking text.
    tui_source = open("app/tui/app.py", encoding="utf-8").read()
    assert "_thinking_chunk_from_worker" in tui_source
    assert "reasoning" in tui_source and "Thinking" in tui_source
    agent_source = open("app/agent/agent.py", encoding="utf-8").read()
    assert "on_thinking=ctx.on_thinking" in agent_source
    server_source = open("app/server.py", encoding="utf-8").read()
    assert "thinking_delta" in server_source
    print("[PASS] TUI counts reasoning behind the spinner; server streams thinking_delta records")


    from app.tui.app import RazaTUI, StreamingMessage

    verbs = RazaTUI.THINKING_VERBS
    assert len(verbs) >= 40 and len(set(verbs)) == len(verbs), "verbs must be unique and plentiful"
    for flavour in ("Cogitating", "Brewing", "Scampering", "Lollygagging"):
        assert flavour in verbs, flavour
    assert RazaTUI.THINKING_VERB_SECONDS >= 1.0  # Readable, not a strobe
    for required in (
        "_start_thinking_verbs",       # Begins when the assistant bubble mounts
        "_stop_thinking_verbs",        # ends with the turn
        "show_thinking",               # label rendered inside the bubble
        "stop_thinking",
        "thinking-label",              # Dim styling, distinct from content
    ):
        assert required in tui_source, required
    # The verb must stop the moment real content streams: _stream_chunk_ui
    # stops the verb timer before the first append_chunk.
    stream_ui = tui_source.split("def _stream_chunk_ui")[1].split("def ")[0]
    assert "_thinking_verb_timer.stop()" in stream_ui
    # The label lives outside _stream_text so it can never leak into answers.
    assert "self._stream_text += str(chunk" in tui_source
    print("[PASS] message bubble animates Claude-Code thinking words until the answer streams")

    print("=" * 78)
    print("STEP 20.15.2 HIDDEN THINKING STREAM PASSED")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
