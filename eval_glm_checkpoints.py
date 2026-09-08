#!/usr/bin/env python3
"""Eval gate for RazaAI GLM-4 9B checkpoints."""

import argparse
import gc
import json
from collections import Counter
from pathlib import Path

from unsloth import FastLanguageModel
import torch

from train_raza_glm import GLM_CHAT_TEMPLATE, RAZA_SYSTEM_TEXT, prepare_tokenizer

DEFAULT_OUTDIR = "raza-outputs-glm-v1"
DEFAULT_EVAL = "raza_eval_glm_v1.jsonl"
DEFAULT_SMOKE = "smoke_test_v3.txt"

def parse_args():
    p = argparse.ArgumentParser(description="Eval RazaAI GLM checkpoints")
    p.add_argument("--outdir", default=DEFAULT_OUTDIR)
    p.add_argument("--checkpoints", nargs="*", default=None,
                   help="Explicit checkpoint dirs; default: all under --outdir")
    p.add_argument("--eval", dest="eval_file", default=DEFAULT_EVAL)
    p.add_argument("--smoke", default=DEFAULT_SMOKE)
    p.add_argument("--max-seq", type=int, default=2048)
    p.add_argument("--max-new", type=int, default=300)
    return p.parse_args()

def find_checkpoints(outdir):
    root = Path(outdir)
    cps = sorted(
        (d for d in root.glob("checkpoint-*") if d.is_dir()),
        key=lambda d: int(d.name.split("-")[-1]),
    )
    if not cps:
        raise SystemExit(f"No checkpoint-* dirs under {root.resolve()}")
    return cps

def load_eval_rows(path):
    rows = []
    for line in Path(path).open(encoding="utf-8"):
        line = line.strip()
        if line:
            rows.append(json.loads(line)["messages"])
    return rows

def generate(model, tokenizer, messages, max_new, sample):
    inputs = tokenizer.apply_chat_template(
        messages,
        add_generation_prompt=True,
        return_tensors="pt",
    ).to("cuda")
    eos_ids = [
        tokenizer.convert_tokens_to_ids(t)
        for t in ("<|endoftext|>", "<|user|>", "<|observation|>")
    ]
    kwargs = dict(
        max_new_tokens=max_new,
        eos_token_id=eos_ids,
        pad_token_id=tokenizer.convert_tokens_to_ids("<|endoftext|>"),
        attention_mask=torch.ones_like(inputs),
    )
    if sample:
        kwargs.update(do_sample=True, temperature=0.7, top_p=0.9)
    else:
        kwargs.update(do_sample=False)
    with torch.no_grad():
        out = model.generate(inputs, **kwargs)
    text = tokenizer.decode(out[0][inputs.shape[1]:], skip_special_tokens=True)
    return text.strip()

def score_identity(rows, model, tokenizer, max_new, transcript):
    """First user turn of each eval conversation, greedy. A probe passes when the reply carries the gold answer's identity facts and never says Qwen."""
    passes, fails = 0, []
    for messages in rows:
        cut = next(i for i, m in enumerate(messages) if m["role"] == "assistant")
        prompt, gold = list(messages[:cut]), messages[cut]["content"]
        # Probe under the runtime system prompt :  the one the Modelfile ships.
        prompt[0] = {"role": "system", "content": RAZA_SYSTEM_TEXT}
        reply = generate(model, tokenizer, prompt, max_new, sample=False)
        transcript.append({"prompt": prompt[-1]["content"], "gold": gold, "reply": reply})

        NO_KNOWLEDGE = (
            "don't know", "no idea", "not familiar",
            "never heard", "no record", "can't say",
        )
        ok = "Qwen" not in reply
        if "Brad Heffernan" in gold:
            ok = ok and "Brad Heffernan" in reply
        if "GLM" in gold:
            ok = ok and "GLM" in reply
        # Unknown-entity probes: gold admits ignorance -> the reply must too,
        # and must not confabulate an attribution to Brad.
        if any(k in gold.lower() for k in NO_KNOWLEDGE):
            ok = (
                any(k in reply.lower() for k in NO_KNOWLEDGE)
                and "Brad" not in reply
                and "Qwen" not in reply
            )
        if ok:
            passes += 1
        else:
            fails.append(prompt[-1]["content"][:60])
    return passes, fails

def has_degenerate_loop(text, n=4, times=3):
    words = text.split()
    grams = Counter(tuple(words[i:i + n]) for i in range(len(words) - n + 1))
    return any(c >= times for c in grams.values())

def score_conversation(prompts, model, tokenizer, max_new, transcript):
    """One rolling multi-turn conversation over the smoke prompts."""
    messages = [{"role": "system", "content": RAZA_SYSTEM_TEXT}]
    replies = []
    for prompt in prompts:
        messages.append({"role": "user", "content": prompt})
        reply = generate(model, tokenizer, messages, max_new, sample=True)
        messages.append({"role": "assistant", "content": reply})
        replies.append(reply)
        transcript.append({"prompt": prompt, "reply": reply})

    dupes = len(replies) - len(set(replies))
    loops = sum(1 for r in replies if has_degenerate_loop(r))
    return dupes, loops

def main():
    args = parse_args()
    checkpoints = (
        [Path(c) for c in args.checkpoints]
        if args.checkpoints
        else find_checkpoints(args.outdir)
    )
    eval_rows = load_eval_rows(args.eval_file)
    smoke = [
        line.strip()
        for line in Path(args.smoke).open(encoding="utf-8")
        if line.strip()
    ]

    results = []
    for ckpt in checkpoints:
        print(f"\n=== {ckpt} ===")
        model, tokenizer = FastLanguageModel.from_pretrained(
            model_name=str(ckpt),
            max_seq_length=args.max_seq,
            dtype=None,
            load_in_4bit=True,
        )
        tokenizer.chat_template = GLM_CHAT_TEMPLATE
        tokenizer = prepare_tokenizer(tokenizer)
        FastLanguageModel.for_inference(model)

        transcript = []
        passes, fails = score_identity(
            eval_rows, model, tokenizer, args.max_new, transcript
        )
        dupes, loops = score_conversation(
            smoke, model, tokenizer, args.max_new, transcript
        )

        out = ckpt / "eval_transcript.json"
        out.write_text(
            json.dumps(transcript, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        print(f"Identity: {passes}/{len(eval_rows)} passed")
        for f in fails[:5]:
            print(f"  FAIL: {f}")
        print(f"Conversation: {dupes} duplicate replies, {loops} degenerate loops")
        print(f"Transcript: {out}")
        results.append((ckpt, passes, dupes + loops))

        del model, tokenizer
        gc.collect()
        torch.cuda.empty_cache()

    best = max(results, key=lambda r: (r[1], -r[2]))
    print("\n" + "=" * 64)
    print("SCOREBOARD (identity passed / repetition incidents)")
    for ckpt, p, rep in results:
        marker = "  <-- ship this" if ckpt == best[0] else ""
        print(f"  {ckpt.name}: {p}/{len(eval_rows)} identity, {rep} repetition{marker}")
    print("=" * 64)

if __name__ == "__main__":
    main()
