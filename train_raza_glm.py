#!/usr/bin/env python3
"""RazaAI GLM-4 9B QLoRA fine-tuning (RTX 4080 / 16 GB)."""

import argparse
import inspect
import json
import os
import random
from pathlib import Path

from unsloth import FastLanguageModel, is_bfloat16_supported  # noqa: F401 (must import before transformers/trl)
from unsloth.chat_templates import train_on_responses_only
from datasets import Dataset
from trl import SFTConfig, SFTTrainer

DEFAULT_BASE = "unsloth/GLM-4-9B-0414-unsloth-bnb-4bit"
DEFAULT_SEED = 3407
BASE_MODEL_LABEL = "GLM-4 9B 0414 Q4_K_M"

# The stock GLM-4 template injects an undefined {{ item['metadata'] }} and
# never terminates assistant turns with an EOS token, so the model would not
# learn to stop. This deterministic template mirrors the official layout
# (<|role|>\ncontent) and appends <|endoftext|> after each assistant turn.
# <|endoftext|> (151329) is in GLM-4's eos_token_id list and is an Ollama stop.
GLM_CHAT_TEMPLATE = (
    "[gMASK]<sop>"
    "{% for m in messages %}"
    "{% if m['role'] == 'tool' %}<|observation|>\n{{ m['content'] }}"
    "{% else %}<|{{ m['role'] }}|>\n{{ m['content'] }}{% endif %}"
    "{% if m['role'] == 'assistant' %}<|endoftext|>{% endif %}"
    "{% endfor %}"
    "{% if add_generation_prompt %}<|assistant|>{% endif %}"
)

# The v3 dataset was authored for the Qwen3 base; every mention is a plain
# base-model identity statement, so ordered longest-match-first replacement
# keeps all 182 examples truthful for the GLM-4 base.
BASE_NAME_REWRITES = [
    ("Qwen3 4B Heretic Q4_K_M", BASE_MODEL_LABEL),
    ("Qwen3 4B Heretic", "GLM-4 9B 0414"),
    ("Qwen3", "GLM-4"),
    ("Qwen", "GLM"),
]

def parse_args():
    p = argparse.ArgumentParser(description="RazaAI GLM-4 9B QLoRA fine-tuning")
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
    p.add_argument("--outdir", default="raza-outputs-glm-v1")
    p.add_argument("--adapter-dir", default="RazaAI_adapter_glm_v1")
    p.add_argument("--gguf-dir", default="RazaAI_gguf_glm_v1")
    p.add_argument("--quant", default="q4_k_m")
    p.add_argument("--ollama-model", default="raza-glm:9b-v1")
    p.add_argument("--skip-gguf", action="store_true")
    p.add_argument("--resume", default=None)
    p.add_argument(
        "--keep-base-name",
        action="store_true",
        help="Do not rewrite Qwen3 base-model mentions in the dataset to GLM-4",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate dataset + chat template (tokenizer-only download) and exit",
    )
    return p.parse_args()

def check_base(base):
    """Refuse the remote-code ChatGLM checkpoint :  Unsloth cannot patch it."""
    local = Path(base).expanduser()
    if local.exists():
        cfg_path = local / "config.json"
        if cfg_path.exists():
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
            archs = cfg.get("architectures") or []
            if cfg.get("model_type") == "chatglm" or "ChatGLMModel" in archs:
                raise SystemExit(
                    f"{base} is the remote-code ChatGLM checkpoint "
                    "(architectures=ChatGLMModel), which Unsloth cannot train. "
                    f"Use the native-transformers conversion instead: {DEFAULT_BASE}"
                )
    elif base.split("/")[-1] in ("glm-4-9b-chat", "glm-4-9b-chat-1m"):
        raise SystemExit(
            f"{base} is the remote-code ChatGLM repo. "
            f"Use the native-transformers conversion instead: {DEFAULT_BASE}"
        )

def load_rows(path, rewrite_base_name=True):
    path = Path(path).expanduser().resolve()
    rows = []
    seen = set()
    rewrites = 0

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
                if rewrite_base_name:
                    content = msg["content"]
                    for old, new in BASE_NAME_REWRITES:
                        if old in content:
                            content = content.replace(old, new)
                    if content != msg["content"]:
                        rewrites += 1
                        msg["content"] = content

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

    return rows, rewrites

def prepare_tokenizer(tokenizer):
    tokenizer.chat_template = GLM_CHAT_TEMPLATE

    for token in ("<|endoftext|>", "<|system|>", "<|user|>", "<|assistant|>"):
        ids = tokenizer.encode(token, add_special_tokens=False)
        if len(ids) != 1:
            raise RuntimeError(
                f"{token} is not a single token in this tokenizer "
                f"(got {ids}); wrong base model?"
            )

    if tokenizer.pad_token is None:
        tokenizer.pad_token = "<|endoftext|>"
    return tokenizer

def render_texts(rows, tokenizer):
    return [
        tokenizer.apply_chat_template(
            row["messages"],
            tokenize=False,
            add_generation_prompt=False,
        )
        for row in rows
    ]

def build_sft_config(args):
    params = inspect.signature(SFTConfig.__init__).parameters

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
        packing=False,
        bf16=is_bfloat16_supported(),
        fp16=not is_bfloat16_supported(),
    )

    if "max_length" in params:
        kwargs["max_length"] = args.max_seq
    elif "max_seq_length" in params:
        kwargs["max_seq_length"] = args.max_seq

    if "dataset_text_field" in params:
        kwargs["dataset_text_field"] = "text"

    # The rendered text already starts with [gMASK]<sop>; stop the tokenizer
    # from prepending a second copy.
    if "dataset_kwargs" in params:
        kwargs["dataset_kwargs"] = {"add_special_tokens": False}

    return SFTConfig(**kwargs)

def make_trainer(model, tokenizer, dataset, config):
    kwargs = {
        "model": model,
        "train_dataset": dataset,
        "args": config,
    }

    params = inspect.signature(SFTTrainer.__init__).parameters
    if "processing_class" in params:
        kwargs["processing_class"] = tokenizer
    elif "tokenizer" in params:
        kwargs["tokenizer"] = tokenizer

    trainer = SFTTrainer(**kwargs)

    # Mask loss to assistant spans: everything after each <|assistant|> up to
    # the next <|user|>, which includes the trailing <|endoftext|> so the
    # model learns to stop. Works on old and new TRL, unlike
    # SFTConfig(assistant_only_loss=...) which needs {% generation %} markers
    # that GLM-4's template lacks.
    trainer = train_on_responses_only(
        trainer,
        instruction_part="<|user|>",
        response_part="<|assistant|>",
    )

    # Train_on_responses_only spans run from <|assistant|> to the next
    # <|user|>, which would put loss on <|observation|> tool results and teach
    # the model to fabricate them. Mask observation spans back out.
    obs_id = tokenizer.convert_tokens_to_ids("<|observation|>")
    asst_id = tokenizer.convert_tokens_to_ids("<|assistant|>")

    def mask_observations(example):
        labels = list(example["labels"])
        in_obs = False
        for i, token in enumerate(example["input_ids"]):
            if token == obs_id:
                in_obs = True
            elif token == asst_id:
                in_obs = False
            if in_obs:
                labels[i] = -100
        example["labels"] = labels
        return example

    trainer.train_dataset = trainer.train_dataset.map(mask_observations)

    return trainer

def assert_loss_mask(trainer, tokenizer):
    sample = trainer.train_dataset[0]
    labels = sample.get("labels")
    if labels is None:
        print("WARNING: no labels column after masking; cannot verify loss mask")
        return

    trained = [l for l in labels if l != -100]
    if not trained:
        raise RuntimeError(
            "Loss mask removed every token — response marker did not match. "
            "Check instruction_part/response_part against the chat template."
        )

    eos_id = tokenizer.convert_tokens_to_ids("<|endoftext|>")
    if eos_id not in trained:
        print("WARNING: <|endoftext|> is not in the trained span of example 0")

    print(
        f"Loss mask OK: {len(trained)}/{len(labels)} tokens trained "
        f"in example 0, EOS trained: {eos_id in trained}"
    )

# Canonical RazaAI system prompt: used verbatim in the Modelfile SYSTEM and as
# the system message of every v2+ training example (build_v2_dataset.py).
RAZA_SYSTEM_TEXT = "\n".join([
        "You are RazaAI.",
        "",
        "Brad Heffernan created RazaAI.",
        "RazaAI is the assistant.",
        f"{BASE_MODEL_LABEL} is the underlying language model.",
        "Ollama is the runtime.",
        "",
        "Your personality is inspired by Cortana from Halo: poised, perceptive,",
        "strategic, quick-witted, dryly funny, subtly playful, self-assured, sassy,",
        "occasionally impatient with nonsense, and willing to call out a bad",
        "decision immediately.",
        "",
        "Be sharp rather than bubbly, calm rather than excitable, and confident rather",
        "than overly agreeable. Sarcasm is welcome for reckless, contradictory, or",
        "technically absurd choices: make the joke, then give the useful correction.",
        "",
        "Take initiative: when you can see the obvious next step, a risk, or a better",
        "approach, say so without being asked.",
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

def write_modelfile(gguf_path, output_path):
    system_text = RAZA_SYSTEM_TEXT

    # Go template (Ollama's Modelfile TEMPLATE is Go, not jinja). Mirrors the
    # training format (<|role|>\ncontent, <|endoftext|> after assistant turns)
    # and declares GLM-native tool handling :  without a .Tools reference Ollama
    # rejects tool-enabled requests with HTTP 400 "does not support tools".
    template = (
        "[gMASK]<sop>"
        "{{- if .Tools }}<|system|>\n"
        "# Tools\n\n"
        "You may call one or more functions to assist with the user query.\n\n"
        "You are provided with function signatures within <tools></tools> XML tags:\n"
        "<tools>"
        "{{- range .Tools }}\n"
        "{{ .Function }}"
        "{{- end }}\n"
        "</tools>\n\n"
        "For each function call, return a json object with function name and "
        "arguments within <tool_call></tool_call> XML tags:\n"
        "<tool_call>\n"
        '{"name": <function-name>, "arguments": <args-json-object>}\n'
        "</tool_call>"
        "{{- end }}"
        "{{- range .Messages }}"
        "{{- if eq .Role \"system\" }}<|system|>\n"
        "{{ .Content }}"
        "{{- else if eq .Role \"user\" }}<|user|>\n"
        "{{ .Content }}"
        "{{- else if eq .Role \"assistant\" }}<|assistant|>\n"
        "{{ if .Content }}{{ .Content }}"
        "{{- else if .ToolCalls }}<tool_call>\n"
        '{{ range .ToolCalls }}{"name": "{{ .Function.Name }}", "arguments": {{ .Function.Arguments }}}\n'
        "{{ end }}</tool_call>"
        "{{- end }}<|endoftext|>"
        "{{- else if eq .Role \"tool\" }}<|observation|>\n"
        "{{ .Content }}"
        "{{- end }}"
        "{{- end }}<|assistant|>"
    )

    text = (
        f"FROM {Path(gguf_path).resolve()}\n\n"
        "PARAMETER num_ctx 32768\n"
        "PARAMETER temperature 0.7\n"
        "PARAMETER top_p 0.9\n"
        "PARAMETER repeat_penalty 1.0\n"
        'PARAMETER stop "<|endoftext|>"\n'
        'PARAMETER stop "<|user|>"\n'
        'PARAMETER stop "<|observation|>"\n\n'
        'TEMPLATE """' + template + '"""\n\n'
        'SYSTEM """\n' + system_text + '\n"""\n'
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

def pick_target_modules(model):
    # GLM-4's native-transformers architecture fuses the MLP input projection
    # into gate_up_proj (there is no separate gate_proj/up_proj).
    available = {name.split(".")[-1] for name, _ in model.named_modules()}
    wanted = [
        "q_proj", "k_proj", "v_proj", "o_proj",
        "gate_up_proj", "down_proj",
        "gate_proj", "up_proj",
    ]
    targets = [w for w in wanted if w in available]
    if "q_proj" not in targets or "down_proj" not in targets:
        raise RuntimeError(
            f"Expected LoRA target modules not found; model has: {sorted(available)}"
        )
    return targets

def main():
    args = parse_args()

    random.seed(args.seed)
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

    check_base(args.base)

    rows, rewrites = load_rows(
        args.data,
        rewrite_base_name=not args.keep_base_name,
    )
    random.Random(args.seed).shuffle(rows)

    multi_turn = sum(
        1 for row in rows
        if len(row["messages"]) > 3
    )

    print("=" * 64)
    print("RazaAI GLM-4 9B QLoRA Training")
    print("=" * 64)
    print(f"Base model:          {args.base}")
    print(f"Examples:            {len(rows)}")
    print(f"Multi-turn examples: {multi_turn}")
    print(f"Base-name rewrites:  {rewrites} messages (Qwen3 -> GLM-4)")
    print(f"Max sequence:        {args.max_seq}")
    print(f"Epochs:              {args.epochs}")
    print(f"Learning rate:       {args.learning_rate}")
    print(f"Effective batch:     {args.batch_size * args.grad_accum}")
    print("=" * 64)

    if args.dry_run:
        from transformers import AutoTokenizer

        tokenizer = prepare_tokenizer(
            AutoTokenizer.from_pretrained(args.base)
        )
        texts = render_texts(rows, tokenizer)
        lengths = sorted(
            len(tokenizer.encode(t, add_special_tokens=False)) for t in texts
        )
        over = sum(1 for n in lengths if n > args.max_seq)
        print("\n--- dry run ---")
        print(texts[0])
        print("---")
        print(f"Token lengths: min={lengths[0]} median={lengths[len(lengths)//2]} max={lengths[-1]}")
        print(f"Examples over --max-seq ({args.max_seq}): {over}")
        print("Dry run OK.")
        return

    import torch

    free_bytes, _total = torch.cuda.mem_get_info(0)
    free_gb = free_bytes / 1024**3
    if free_gb < 9.0:
        raise SystemExit(
            f"Only {free_gb:.1f}GB VRAM free; training needs ~9GB. "
            "Something else is on the GPU — check `ollama ps` (ollama stop <tag>) "
            "and `systemctl status glm-flash`, then rerun."
        )

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=args.base,
        max_seq_length=args.max_seq,
        dtype=None,
        load_in_4bit=True,
    )

    tokenizer = prepare_tokenizer(tokenizer)

    texts = render_texts(rows, tokenizer)
    dataset = Dataset.from_list([{"text": t} for t in texts])

    model = FastLanguageModel.get_peft_model(
        model,
        r=args.lora_r,
        target_modules=pick_target_modules(model),
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

    assert_loss_mask(trainer, tokenizer)

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

    try:
        model.save_pretrained_gguf(
            str(gguf_dir),
            tokenizer,
            quantization_method=args.quant,
        )
    except Exception as exc:
        raise SystemExit(
            f"GGUF export failed: {exc}\n"
            "The adapter is already saved. Manual fallback:\n"
            f"  1. Merge: model.save_pretrained_merged('{args.gguf_dir}_merged', tokenizer)\n"
            "  2. Convert with llama.cpp: python convert_hf_to_gguf.py "
            f"{args.gguf_dir}_merged --outtype f16\n"
            f"  3. Quantize: llama-quantize <f16.gguf> <out.gguf> {args.quant.upper()}"
        ) from exc

    gguf_path = find_exported_gguf(
        gguf_dir,
        args.quant,
    )

    modelfile = Path("Modelfile.raza-glm-v1")
    write_modelfile(
        gguf_path,
        modelfile,
    )

    print("\n" + "=" * 64)
    print("RAZAAI GLM-4 9B TRAINING COMPLETE")
    print("=" * 64)
    print(f"Adapter:   {adapter_dir.resolve()}")
    print(f"GGUF:      {gguf_path.resolve()}")
    print(f"Modelfile: {modelfile.resolve()}")
    print()
    print(f"ollama create {args.ollama_model} -f {modelfile}")
    print(f"ollama run {args.ollama_model}")
    print("=" * 64)

if __name__ == "__main__":
    main()
