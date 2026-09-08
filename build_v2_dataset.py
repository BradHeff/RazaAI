#!/usr/bin/env python3
"""Assemble raza_train_glm_v2.jsonl."""

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

from train_raza_glm import BASE_NAME_REWRITES, RAZA_SYSTEM_TEXT

BANNED_SUBSTRINGS = [
    "Qwen",
    "As an AI",
    "as an AI language model",
    "How can I assist",
    "Feel free to",
    "feel free to reach out",
    "I'm sorry, but I can't",
]

def iter_rows(path):
    for line_no, raw in enumerate(Path(path).open(encoding="utf-8"), 1):
        raw = raw.strip()
        if not raw:
            continue
        try:
            yield line_no, json.loads(raw)
        except json.JSONDecodeError as exc:
            print(f"  DROP {path}:{line_no}: bad JSON: {exc}")

def validate(messages, source, line_no, errors):
    def drop(reason):
        errors.append(f"{source}:{line_no}: {reason}")
        return None

    if not isinstance(messages, list) or len(messages) < 3:
        return drop("too few messages")
    if messages[0].get("role") != "system":
        return drop("first message not system")
    body = messages[1:]
    if body[0].get("role") != "user":
        return drop("first turn after system must be user")
    if body[-1].get("role") != "assistant":
        return drop("conversation must end on assistant")
    # User -> assistant; assistant -> user or tool (tool-call turns);
    # tool -> assistant.
    allowed_next = {"user": {"assistant"}, "assistant": {"user", "tool"}, "tool": {"assistant"}}
    for i, msg in enumerate(body):
        role = msg.get("role")
        if role not in allowed_next:
            return drop(f"turn {i + 1} unknown role {role!r}")
        if i and role not in allowed_next[body[i - 1]["role"]]:
            return drop(f"turn {i + 1} role {role!r} after {body[i - 1]['role']!r}")
        content = msg.get("content")
        if not isinstance(content, str) or not content.strip():
            return drop(f"turn {i + 1} empty content")
        for bad in BANNED_SUBSTRINGS:
            if bad.lower() in content.lower():
                return drop(f"banned phrase {bad!r}")
    return messages

def normalize_user_key(messages):
    first_user = next(m["content"] for m in messages if m["role"] == "user")
    return re.sub(r"[^a-z0-9]+", " ", first_user.lower()).strip()

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--gen-dir", required=True, help="Directory of generated category .jsonl files")
    p.add_argument("--original", default="raza_train_v3.jsonl")
    p.add_argument("--out", default="raza_train_glm_v2.jsonl")
    args = p.parse_args()

    rows = []
    errors = []
    seen_exact = set()
    seen_first_user = set()
    per_source = Counter()

    def add(messages, source, line_no, enforce_user_key=True):
        messages = validate(messages, source, line_no, errors)
        if messages is None:
            return
        fingerprint = json.dumps(messages, ensure_ascii=False, sort_keys=True)
        if fingerprint in seen_exact:
            errors.append(f"{source}:{line_no}: exact duplicate")
            return
        user_key = normalize_user_key(messages)
        # Originals may legitimately share a first user message with divergent
        # continuations; generated rows may not collide with anything.
        if enforce_user_key and user_key in seen_first_user:
            errors.append(f"{source}:{line_no}: duplicate first user message")
            return
        seen_exact.add(fingerprint)
        seen_first_user.add(user_key)
        per_source[source] += 1
        rows.append({"messages": messages})

    # Originals: rewrite base-model names, upgrade the system prompt.
    for line_no, obj in iter_rows(args.original):
        messages = obj["messages"]
        for msg in messages:
            for old, new in BASE_NAME_REWRITES:
                msg["content"] = msg["content"].replace(old, new)
        messages[0]["content"] = RAZA_SYSTEM_TEXT
        add(messages, "v3-original", line_no, enforce_user_key=False)

    # Generated batches: inject the canonical system prompt.
    gen_files = sorted(Path(args.gen_dir).glob("*.jsonl"))
    if not gen_files:
        sys.exit(f"No .jsonl files in {args.gen_dir}")
    for path in gen_files:
        for line_no, obj in iter_rows(path):
            messages = obj.get("messages", [])
            if messages and "__SYS__" in str(messages[0].get("content", "")):
                messages[0]["content"] = messages[0]["content"].replace(
                    "__SYS__", RAZA_SYSTEM_TEXT
                )
            add(messages, path.stem, line_no)

    with Path(args.out).open("w", encoding="utf-8") as out:
        for row in rows:
            out.write(json.dumps(row, ensure_ascii=False) + "\n")

    multi_turn = sum(1 for r in rows if len(r["messages"]) > 3)
    print(f"\nWrote {args.out}: {len(rows)} examples ({multi_turn} multi-turn)")
    for source, count in sorted(per_source.items()):
        print(f"  {source}: {count}")
    print(f"Dropped/deduped: {len(errors)}")
    for e in errors[:20]:
        print(f"  {e}")
    if len(errors) > 20:
        print(f"  ... and {len(errors) - 20} more")

if __name__ == "__main__":
    main()
