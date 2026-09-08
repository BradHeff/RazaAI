#!/usr/bin/env python3
"""RazaAI-Coder v2 QLoRA training (host RTX 4080)."""

import argparse
import inspect
import json
import os
import random
import shutil
import subprocess
from pathlib import Path

DEFAULT_BASE = "Qwen/Qwen2.5-Coder-7B-Instruct"
DRY_RUN_BASE = "Qwen/Qwen2.5-Coder-0.5B-Instruct"
DEFAULT_SEED = 3407

CODER_SYSTEM = """You are RazaAI-Coder, the coding component of RazaAI, created by Brad Heffernan.
RazaAI began in 2019 as a simple language model built by Brad Heffernan; development resumed in 2024.
You run on a Qwen2.5-Coder 7B model under Ollama.

You plan code changes; the RazaAI application performs every write, runs every
test, and reports the real result. Never claim code was written, executed, tested
or successful — you cannot know that. When asked for a plan, return only the JSON
the application specifies: exact file paths, exact patch anchors copied verbatim
from the supplied source, complete content for new files. Add to existing files
with mode=append or a provided anchor; never replace an existing definition with a
new one. Implement exactly what was requested with the names the user used.
Preserve the project's existing style, imports and public API. Never include secrets."""


def parse_args():
    p = argparse.ArgumentParser(description="RazaAI-Coder v2 QLoRA fine-tuning")
    p.add_argument("--base", default=DEFAULT_BASE)
    p.add_argument("--data", default="training/coder_v2_seed/coder_v2.jsonl")
    p.add_argument("--epochs", type=float, default=3.0)
    p.add_argument("--max-seq", type=int, default=6144)
    p.add_argument("--batch-size", type=int, default=1)
    p.add_argument("--grad-accum", type=int, default=8)
    p.add_argument("--learning-rate", type=float, default=1e-4)
    p.add_argument("--warmup-steps", type=int, default=5)
    p.add_argument("--lora-r", type=int, default=16)
    p.add_argument("--lora-alpha", type=int, default=32)
    p.add_argument("--seed", type=int, default=DEFAULT_SEED)
    p.add_argument("--outdir", default="raza-coder-outputs-v2")
    p.add_argument("--adapter-dir", default="RazaAI_coder_adapter_v2")
    p.add_argument("--gguf-dir", default="RazaAI_coder_gguf_v2")
    p.add_argument("--quant", default="q4_k_m")
    p.add_argument("--deploy-gguf", default="model/raza-coder-3b-v2.Q4_K_M.gguf")
    p.add_argument("--modelfile", default="Modelfile.raza-coder-3b-v2")
    p.add_argument("--ollama-model", default="raza-coder:3b-v1-v2")
    p.add_argument("--skip-gguf", action="store_true")
    p.add_argument("--skip-ollama", action="store_true")
    p.add_argument("--resume", default=None)
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="0.5B base, 1 epoch, tag raza-coder:dryrun — proves the pipeline",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="train even when the seed is small or homogeneous (see seed_guard)",
    )
    args = p.parse_args()
    if args.dry_run:
        args.base = DRY_RUN_BASE
        args.epochs = 1.0
        args.adapter_dir += "-dryrun"
        args.gguf_dir += "-dryrun"
        args.outdir += "-dryrun"
        args.deploy_gguf = "model/raza-coder-dryrun.Q4_K_M.gguf"
        args.modelfile = "Modelfile.raza-coder-dryrun"
        args.ollama_model = "raza-coder:dryrun"
    return args


def load_rows(path):
    path = Path(path).expanduser().resolve()
    rows, seen = [], set()
    with path.open("r", encoding="utf-8") as handle:
        for line_no, raw in enumerate(handle, 1):
            raw = raw.strip()
            if not raw:
                continue
            obj = json.loads(raw)
            messages = obj.get("messages")
            if not isinstance(messages, list) or len(messages) < 3:
                raise ValueError(
                    f"{path}:{line_no}: expected system + user + assistant messages"
                )
            roles = [m.get("role") for m in messages]
            if roles[0] != "system" or "user" not in roles or "assistant" not in roles:
                raise ValueError(
                    f"{path}:{line_no}: roles must be system, user, assistant"
                )
            for msg in messages:
                if (
                    not isinstance(msg.get("content"), str)
                    or not msg["content"].strip()
                ):
                    raise ValueError(
                        f"{path}:{line_no}: each message needs non-empty content"
                    )
            # The assistant turn must be a JSON plan :  that is the behaviour being taught
            try:
                plan = json.loads(messages[-1]["content"])
                assert isinstance(plan.get("files"), list)
            except (ValueError, AssertionError) as exc:
                raise ValueError(
                    f"{path}:{line_no}: assistant content is not a JSON plan: {exc}"
                ) from exc
            fingerprint = json.dumps(messages, ensure_ascii=False, sort_keys=True)
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            rows.append({"messages": messages})
    if not rows:
        raise ValueError("No valid training examples loaded")
    return rows


MIN_EXAMPLES = 100
MIN_DISTINCT_REQUEST_SHAPES = 6


def seed_guard(rows, force, dry_run):
    """A tiny or single-habit seed replaces the model's judgement with one reflex (v2 measured 1/9 after 17 near-identical examples). Refuse unless forced."""
    import re

    shapes = set()
    for row in rows:
        user = next((m["content"] for m in row["messages"] if m["role"] == "user"), "")
        req = user.split("\n", 1)[0].replace("REQUEST: ", "")
        shapes.add(re.sub(r"\b\w*\d+\w*\b", "N", req.casefold())[:60])
    problems = []
    if len(rows) < MIN_EXAMPLES:
        problems.append(f"{len(rows)} examples (< {MIN_EXAMPLES})")
    if len(shapes) < MIN_DISTINCT_REQUEST_SHAPES:
        problems.append(
            f"{len(shapes)} distinct request shape(s) (< {MIN_DISTINCT_REQUEST_SHAPES})"
        )
    if problems and not (force or dry_run):
        raise SystemExit(
            "Refusing to train: " + "; ".join(problems) + ".\n"
            "A seed this small/homogeneous over-fits into a single reflex (v2: 1/9 on the coding eval).\n"
            "Grow the seed (more stress/eval runs with RAZAAI_CODER_TRACE=1, real repos, commit-to-plan)\n"
            "or pass --force with --epochs 1 --learning-rate 5e-5 if you really want to try."
        )
    if problems:
        print("[warn] seed guard bypassed: " + "; ".join(problems))


def drop_too_long(rows, tokenizer, max_seq):
    kept, dropped = [], []
    for row in rows:
        text = tokenizer.apply_chat_template(
            row["messages"], tokenize=False, add_generation_prompt=False
        )
        n = len(tokenizer(text, add_special_tokens=False)["input_ids"])
        (kept if n <= max_seq else dropped).append((n, row))
    if dropped:
        print(
            f"Dropped {len(dropped)} example(s) longer than {max_seq} tokens "
            f"(longest {max(n for n, _ in dropped)}); raise --max-seq or shorten prompts to keep them."
        )
    if not kept:
        raise ValueError("Every example exceeds --max-seq")
    lengths = sorted(n for n, _ in kept)
    print(
        f"Token lengths: min {lengths[0]}  median {lengths[len(lengths) // 2]}  max {lengths[-1]}"
    )
    return [row for _, row in kept]


def build_sft_config(args, is_bf16):
    from trl import SFTConfig

    params = inspect.signature(SFTConfig.__init__).parameters
    if "assistant_only_loss" not in params:
        raise RuntimeError(
            "TRL does not expose assistant_only_loss; upgrade unsloth and trl (same as v3)."
        )
    kwargs = dict(
        output_dir=args.outdir,
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        num_train_epochs=args.epochs,
        learning_rate=args.learning_rate,
        warmup_steps=args.warmup_steps,
        logging_steps=1,
        save_strategy="epoch",
        optim="adamw_8bit",
        weight_decay=0.01,
        max_grad_norm=1.0,
        lr_scheduler_type="cosine",
        seed=args.seed,
        report_to="none",
        assistant_only_loss=True,
        packing=False,
        bf16=is_bf16,
        fp16=not is_bf16,
    )
    if "max_length" in params:
        kwargs["max_length"] = args.max_seq
    elif "max_seq_length" in params:
        kwargs["max_seq_length"] = args.max_seq
    if "eos_token" in params:
        kwargs["eos_token"] = "<|im_end|>"
    return SFTConfig(**kwargs)


def make_trainer(model, tokenizer, dataset, config):
    from trl import SFTTrainer

    def formatting_func(examples):
        messages = examples["messages"]
        if not messages:
            return []
        conversations = [messages] if isinstance(messages[0], dict) else messages
        return [
            tokenizer.apply_chat_template(
                c, tokenize=False, add_generation_prompt=False
            )
            for c in conversations
        ]

    kwargs = {
        "model": model,
        "train_dataset": dataset,
        "args": config,
        "formatting_func": formatting_func,
    }
    params = inspect.signature(SFTTrainer.__init__).parameters
    kwargs["processing_class" if "processing_class" in params else "tokenizer"] = (
        tokenizer
    )
    return SFTTrainer(**kwargs)


def write_modelfile(gguf_rel, output_path, lineage):
    text = (
        f"# RazaAI-Coder v2 — QLoRA of {lineage} on RazaAI's own coding failures.\n"
        f"FROM {gguf_rel}\n\n"
        "PARAMETER num_ctx 8192\nPARAMETER num_batch 256\nPARAMETER temperature 0.2\n"
        "PARAMETER top_p 0.9\nPARAMETER top_k 40\nPARAMETER repeat_penalty 1.05\n"
        'PARAMETER stop "<|im_end|>"\nPARAMETER stop "<|endoftext|>"\nPARAMETER stop "<|im_start|>"\n\n'
        'SYSTEM """\n' + CODER_SYSTEM + '\n"""\n'
    )
    Path(output_path).write_text(text, encoding="utf-8")


def find_exported_gguf(gguf_dir, quant):
    ggufs = []
    for directory in (Path(gguf_dir), Path(f"{gguf_dir}_gguf")):
        if directory.exists():
            ggufs.extend(directory.glob("*.gguf"))
    if not ggufs:
        raise RuntimeError(f"No GGUF found under {gguf_dir}")
    preferred = [p for p in ggufs if quant.upper() in p.name.upper()] or ggufs
    return sorted(preferred, key=lambda p: p.stat().st_mtime)[-1]


def main():
    args = parse_args()
    random.seed(args.seed)
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

    from datasets import Dataset
    from unsloth import FastLanguageModel, is_bfloat16_supported

    rows = load_rows(args.data)
    seed_guard(rows, args.force, args.dry_run)
    print("=" * 64)
    print("RazaAI-Coder v2 QLoRA Training" + ("  [DRY RUN]" if args.dry_run else ""))
    print("=" * 64)
    print(f"Base model:      {args.base}")
    print(f"Examples:        {len(rows)}")
    print(f"Max sequence:    {args.max_seq}")
    print(f"Epochs:          {args.epochs}")
    print(f"Learning rate:   {args.learning_rate}")
    print(f"Effective batch: {args.batch_size * args.grad_accum}")
    print("=" * 64)

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=args.base,
        max_seq_length=args.max_seq,
        dtype=None,
        load_in_4bit=True,
    )
    if not getattr(tokenizer, "chat_template", None):
        raise RuntimeError("Tokenizer has no chat template; refusing to guess one.")
    if tokenizer.convert_tokens_to_ids("<|im_end|>") not in (None, -1):
        tokenizer.eos_token = "<|im_end|>"

    rows = drop_too_long(rows, tokenizer, args.max_seq)
    random.Random(args.seed).shuffle(rows)
    dataset = Dataset.from_list(rows)

    model = FastLanguageModel.get_peft_model(
        model,
        r=args.lora_r,
        target_modules=[
            "q_proj",
            "k_proj",
            "v_proj",
            "o_proj",
            "gate_proj",
            "up_proj",
            "down_proj",
        ],
        lora_alpha=args.lora_alpha,
        lora_dropout=0.0,
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=args.seed,
        use_rslora=False,
        loftq_config=None,
    )

    trainer = make_trainer(
        model, tokenizer, dataset, build_sft_config(args, is_bfloat16_supported())
    )
    print("\nTraining assistant (plan JSON) tokens only...")
    trainer.train(resume_from_checkpoint=args.resume)

    adapter_dir = Path(args.adapter_dir)
    adapter_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(adapter_dir))
    tokenizer.save_pretrained(str(adapter_dir))
    print(f"\nAdapter saved: {adapter_dir.resolve()}")
    if args.skip_gguf:
        return

    gguf_dir = Path(args.gguf_dir)
    gguf_dir.mkdir(parents=True, exist_ok=True)
    print(f"\nMerging + exporting {args.quant} GGUF (unsloth -> llama.cpp)...")
    model.save_pretrained_gguf(str(gguf_dir), tokenizer, quantization_method=args.quant)
    exported = find_exported_gguf(str(gguf_dir), args.quant)

    deploy = Path(args.deploy_gguf)
    deploy.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(exported, deploy)
    print(
        f"Deployable GGUF: {deploy.resolve()}  ({deploy.stat().st_size / 1e9:.2f} GB)"
    )

    lineage = (
        "Qwen2.5-Coder 0.5B (dry run)" if args.dry_run else "Qwen2.5-Coder 7B Instruct"
    )
    write_modelfile(f"./{deploy.as_posix()}", args.modelfile, lineage)
    print(f"Modelfile:       {Path(args.modelfile).resolve()}")

    if args.skip_ollama:
        return
    if shutil.which("ollama") is None:
        print(
            "ollama not on PATH; create the model later with: "
            f"ollama create {args.ollama_model} -f {args.modelfile}"
        )
        return
    subprocess.run(
        ["ollama", "create", args.ollama_model, "-f", args.modelfile], check=True
    )
    print(f"\nOllama model ready: {args.ollama_model}")
    print("\nNext (adopt only if BOTH improve on v1):")
    print(f"  python3 -m scripts.coding_eval --model {args.ollama_model} --runs 2")
    print(
        f"  RAZAAI_CODE_MODEL={args.ollama_model} python3 -m scripts.stress_session --cycles 10"
    )


if __name__ == "__main__":
    main()
