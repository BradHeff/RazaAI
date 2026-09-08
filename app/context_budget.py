from __future__ import annotations

import json
from copy import deepcopy


import os

# Measured on the Jetson with raza-edge (Qwen3 tokenizer): a 9 718-char
# evidence prompt was 2 388 tokens = 4.07 chars/token. 3.0 keeps a 25 % margin.

# Overrides; `tighten_estimate()` lowers it automatically (never raises it) when
# Ollama's real prompt count proves the estimate optimistic. Ollama's count
# excludes cached prefix tokens, so it can only be trusted in that direction.
_DEFAULT_CHARS_PER_TOKEN = 3.0
_FLOOR_CHARS_PER_TOKEN = 2.0
ESTIMATED_CHARS_PER_TOKEN = max(
    _FLOOR_CHARS_PER_TOKEN, float(os.getenv("RAZAAI_CHARS_PER_TOKEN", "") or _DEFAULT_CHARS_PER_TOKEN)
)


def chars_per_token() -> float:
    return ESTIMATED_CHARS_PER_TOKEN


def tighten_estimate(actual_tokens, estimated_tokens) -> float:
    """If the real count exceeded the estimate, shrink chars/token (down to 2.0)."""
    global ESTIMATED_CHARS_PER_TOKEN
    try:
        actual, est = int(actual_tokens or 0), int(estimated_tokens or 0)
    except (TypeError, ValueError):
        return ESTIMATED_CHARS_PER_TOKEN
    if actual > est > 0:
        ratio = est / actual
        ESTIMATED_CHARS_PER_TOKEN = max(_FLOOR_CHARS_PER_TOKEN, round(ESTIMATED_CHARS_PER_TOKEN * ratio * 0.95, 2))
    return ESTIMATED_CHARS_PER_TOKEN


def estimate_tokens(value) -> int:
    """Dependency-free estimate for Qwen/Ollama chat prompts (see chars/token above)."""
    if value is None:
        return 0
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return max(1, int(len(value) / ESTIMATED_CHARS_PER_TOKEN) + 1)


def estimate_messages(messages) -> int:
    total = 0
    for message in messages or []:
        total += 16  # Qwen role/chat-template overhead
        total += estimate_tokens(message.get("content", ""))
        if message.get("tool_calls"):
            total += estimate_tokens(message["tool_calls"])
    return total


def estimate_tools(tools) -> int:
    if not tools:
        return 0
    return estimate_tokens(tools) + 16


def compact_messages(
    messages,
    *,
    tools=None,
    context_window: int = 4096,
    reserve_output_tokens: int = 700,
    safety_tokens: int = 192,
    aggressive: bool = False,
):
    """Fit an Ollama chat request inside a bounded context window."""
    compacted = deepcopy(list(messages or []))
    window = max(1024, int(context_window or 4096))
    reserve = max(256, int(reserve_output_tokens or 700))
    tool_tokens = estimate_tools(tools)
    prompt_limit = max(512, window - reserve - safety_tokens - tool_tokens)

    before = estimate_messages(compacted)
    removed = 0
    clipped = 0

    # The final user message is the current turn. Historical self.messages are
    # ordinary user/assistant messages before it; drop those oldest-first.
    last_user_index = max(
        (i for i, m in enumerate(compacted) if m.get("role") == "user"),
        default=-1,
    )

    while estimate_messages(compacted) > prompt_limit:
        candidate = None
        for index, message in enumerate(compacted):
            if index == 0 or index == last_user_index:
                continue
            if message.get("role") in {"user", "assistant"}:
                candidate = index
                break
        if candidate is None:
            break
        compacted.pop(candidate)
        removed += 1
        if candidate < last_user_index:
            last_user_index -= 1

    # Current evidence is more valuable than old conversation, but a huge
    # retrieval result should not make the whole turn impossible. Clip evidence
    # payloads from their middle/end while retaining labels and initial facts.
    if estimate_messages(compacted) > prompt_limit:
        for index, message in enumerate(compacted):
            if estimate_messages(compacted) <= prompt_limit:
                break
            if message.get("role") != "tool":
                continue
            content = str(message.get("content") or "")
            clip_at = 700 if aggressive else 1200
            minimum = 850 if aggressive else 1400
            if len(content) <= minimum:
                continue
            message["content"] = (
                content[:clip_at]
                + "\n\n[Context compacted by RazaAI to fit the local model window.]"
            )
            clipped += 1

    # System guidance is authoritative and normally compact already. If a very
    # large operational turn still cannot fit, preserve the beginning (identity,
    # runtime/security contracts) and tail (turn-specific guidance) rather than
    # allowing an Ollama HTTP 400.
    if estimate_messages(compacted) > prompt_limit and compacted:
        system = compacted[0]
        if system.get("role") == "system":
            content = str(system.get("content") or "")
            fraction = 0.58 if aggressive else 0.68
            minimum_chars = 2200 if aggressive else 2800
            allowed_chars = max(
                minimum_chars,
                int(prompt_limit * ESTIMATED_CHARS_PER_TOKEN * fraction),
            )
            if len(content) > allowed_chars:
                head = int(allowed_chars * (0.55 if aggressive else 0.62))
                tail = allowed_chars - head
                system["content"] = (
                    content[:head]
                    + "\n\n[Non-essential system guidance compacted for local context.]\n\n"
                    + content[-tail:]
                )
                clipped += 1

    after = estimate_messages(compacted)
    report = {
        "context_window": window,
        "reserve_output_tokens": reserve,
        "tool_tokens": tool_tokens,
        "prompt_limit_tokens": prompt_limit,
        "estimated_before_tokens": before,
        "estimated_after_tokens": after,
        "history_messages_removed": removed,
        "payloads_clipped": clipped,
        "fits_estimate": after <= prompt_limit,
        "aggressive": bool(aggressive),
    }
    return compacted, report
