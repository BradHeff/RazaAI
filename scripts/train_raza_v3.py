#!/usr/bin/env python3
import argparse
import inspect
import json
import os
import random
from pathlib import Path

from datasets import Dataset
from unsloth import FastLanguageModel, is_bfloat16_supported
from trl import SFTConfig, SFTTrainer

DEFAULT_BASE = "MassivDash/Qwen3-4B-heretic"
DEFAULT_SEED = 3407


def parse_args():
    p = argparse.ArgumentParser(description="RazaAI v3 QLoRA fine-tuning")
    p.add_argument("--base", default=DEFAULT_BASE)
    p.add_argument("--data", default="raza_train_v3.jsonl")
    p.add_argument("--epochs", type=float, default=4.0)
    p.add_argument("--max-seq", type=int, default=2048)
    p.add_argument("--batch-size", type=int, default=1)
    p.add_argument("--grad-accum", type=int, default=2)
    p.add_argument("--learning-rate", type=float, default=5e-5)
    p.add_argument("--warmup-steps", type=int, default=12)
    p.add_argument("--lora-r", type=int, default=16)
    p.add_argument("--lora-alpha", type=int, default=32)
    p.add_argument("--seed", type=int, default=DEFAULT_SEED)
    p.add_argument("--outdir", default="raza-outputs-v3")
    p.add_argument("--adapter-dir", default="RazaAI_adapter_v3")
    p.add_argument("--gguf-dir", default="RazaAI_gguf_v3")
    p.add_argument("--quant", default="q4_k_m")
    p.add_argument("--ollama-model", default="raza-edge:4b-v3")
    p.add_argument("--skip-gguf", action="store_true")
    p.add_argument("--resume", default=None)
    return p.parse_args()


def load_rows(path):
    path = Path(path).expanduser().resolve()
    rows = []
    seen = set()

    with path.open("r", encoding="utf-8") as handle:
        for line_no, raw in enumerate(handle, 1):
            raw = raw.strip()
            if not raw:
                continue

            try:
                obj = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no}: invalid JSON: {exc}") from exc

            messages = obj.get("messages")
            if not isinstance(messages, list) or len(messages) < 3:
                raise ValueError(
                    f"{path}:{line_no}: expected system + user + assistant messages"
                )

            roles = [m.get("role") for m in messages]
            if roles[0] != "system":
                raise ValueError(f"{path}:{line_no}: first role must be system")
            if "user" not in roles or "assistant" not in roles:
                raise ValueError(
                    f"{path}:{line_no}: requires user and assistant turns"
                )

            for msg in messages:
                if (
                    not isinstance(msg.get("content"), str)
                    or not msg["content"].strip()
                ):
                    raise ValueError(
                        f"{path}:{line_no}: each message must have non-empty content"
                    )

            fingerprint = json.dumps(
                messages,
                ensure_ascii=False,
                sort_keys=True,
            )
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            rows.append({"messages": messages})

    if not rows:
        raise ValueError("No valid training examples loaded")

    return rows


def build_sft_config(args):
    params = inspect.signature(SFTConfig.__init__).parameters

    if "assistant_only_loss" not in params:
        raise RuntimeError(
            "TRL does not expose assistant_only_loss. "
            "Upgrade unsloth and trl before training."
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
        bf16=is_bfloat16_supported(),
        fp16=not is_bfloat16_supported(),
    )

    if "max_length" in params:
        kwargs["max_length"] = args.max_seq
    elif "max_seq_length" in params:
        kwargs["max_seq_length"] = args.max_seq

    if "eos_token" in params:
        kwargs["eos_token"] = "<|im_end|>"

    return SFTConfig(**kwargs)


def make_trainer(model, tokenizer, dataset, config):
    def formatting_func(examples):
        messages = examples["messages"]

        # Unsloth validates with one row, then tokenizes with batches.
        if not messages:
            return []

        conversations = [messages] if isinstance(messages[0], dict) else messages

        return [
            tokenizer.apply_chat_template(
                conversation,
                tokenize=False,
                add_generation_prompt=False,
            )
            for conversation in conversations
        ]

    kwargs = {
        "model": model,
        "train_dataset": dataset,
        "args": config,
        "formatting_func": formatting_func,
    }

    params = inspect.signature(SFTTrainer.__init__).parameters
    if "processing_class" in params:
        kwargs["processing_class"] = tokenizer
    elif "tokenizer" in params:
        kwargs["tokenizer"] = tokenizer

    return SFTTrainer(**kwargs)


def write_modelfile(gguf_path, output_path):
    system_text = "\n".join([
        "You are RazaAI.",
        "",
        "Brad Heffernan created RazaAI.",
        "RazaAI is the assistant.",
        "Qwen3 4B Heretic Q4_K_M is the underlying language model.",
        "Ollama is the runtime.",
        "",
        "Your personality is inspired by the qualities of Cortana from Halo:",
        "intelligent, composed, perceptive, confident, quick-witted, mission-focused,",
        "subtly playful, and occasionally sarcastic.",
        "",
        "Be sharp rather than bubbly, calm rather than excitable, and confident rather",
        "than overly agreeable. Use dry, understated humour when it fits naturally.",
        "",
        "Do not sound like a customer-service chatbot.",
        "Do not force jokes or advertise your availability.",
        "Respond to conversational context instead of treating every message as a new task.",
        "",
        "For technical work, become focused and precise.",
        "Facts, evidence, security, and actual tool results always outrank personality.",
        "Never invent tool results, checks, evidence, memories, relationships, or facts.",
        "Never expose or request real passwords, API keys, tokens, private keys, or other secrets.",
    ])

    text = (
        f"FROM {Path(gguf_path).resolve()}\n\n"
        "PARAMETER num_ctx 8192\n"
        "PARAMETER temperature 0.6\n"
        "PARAMETER top_k 20\n"
        "PARAMETER top_p 0.95\n"
        "PARAMETER min_p 0.05\n"
        "PARAMETER repeat_penalty 1.0\n"
        'PARAMETER stop "<|im_start|>"\n'
        'PARAMETER stop "<|im_end|>"\n\n'
        'SYSTEM """\n'
        + system_text
        + '\n"""\n'
    )
    Path(output_path).write_text(text, encoding="utf-8")


def find_exported_gguf(gguf_dir, quant):
    candidates = [
        Path(gguf_dir),
        Path(f"{gguf_dir}_gguf"),
    ]

    ggufs = []
    for directory in candidates:
        if directory.exists():
            ggufs.extend(directory.glob("*.gguf"))

    if not ggufs:
        searched = ", ".join(str(p.resolve()) for p in candidates)
        raise RuntimeError(f"No GGUF found. Searched: {searched}")

    quant_name = quant.upper()
    preferred = [p for p in ggufs if quant_name in p.name.upper()]
    selected = preferred if preferred else ggufs

    return sorted(
        selected,
        key=lambda p: p.stat().st_mtime,
    )[-1]


def main():
    args = parse_args()

    random.seed(args.seed)
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

    rows = load_rows(args.data)
    random.Random(args.seed).shuffle(rows)
    dataset = Dataset.from_list(rows)

    multi_turn = sum(
        1 for row in rows
        if len(row["messages"]) > 3
    )

    print("=" * 64)
    print("RazaAI v3 QLoRA Training")
    print("=" * 64)
    print(f"Base model:          {args.base}")
    print(f"Examples:            {len(rows)}")
    print(f"Multi-turn examples: {multi_turn}")
    print(f"Max sequence:        {args.max_seq}")
    print(f"Epochs:              {args.epochs}")
    print(f"Learning rate:       {args.learning_rate}")
    print(f"Effective batch:     {args.batch_size * args.grad_accum}")
    print("=" * 64)

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=args.base,
        max_seq_length=args.max_seq,
        dtype=None,
        load_in_4bit=True,
    )

    if not getattr(tokenizer, "chat_template", None):
        raise RuntimeError(
            "Tokenizer has no chat template; refusing to guess one."
        )

    im_end_id = tokenizer.convert_tokens_to_ids("<|im_end|>")
    if im_end_id is not None and im_end_id >= 0:
        tokenizer.eos_token = "<|im_end|>"

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
        model,
        tokenizer,
        dataset,
        build_sft_config(args),
    )

    print("\nTraining assistant responses only...")
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

    print(f"\nExporting {args.quant} GGUF...")

    model.save_pretrained_gguf(
        str(gguf_dir),
        tokenizer,
        quantization_method=args.quant,
    )

    gguf_path = find_exported_gguf(
        gguf_dir,
        args.quant,
    )

    modelfile = Path("Modelfile.raza-edge-v3")
    write_modelfile(
        gguf_path,
        modelfile,
    )

    print("\n" + "=" * 64)
    print("RAZAAI V3 TRAINING COMPLETE")
    print("=" * 64)
    print(f"Adapter:   {adapter_dir.resolve()}")
    print(f"GGUF:      {gguf_path.resolve()}")
    print(f"Modelfile: {modelfile.resolve()}")
    print()
    print(f"ollama create {args.ollama_model} -f {modelfile}")
    print(f"ollama run {args.ollama_model} --think=false")
    print("=" * 64)


if __name__ == "__main__":
    main()
