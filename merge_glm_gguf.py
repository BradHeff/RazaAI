#!/usr/bin/env python3
"""Merge a RazaAI GLM QLoRA checkpoint into the bf16 base and export Q4_K_M GGUF."""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

from train_raza_glm import write_modelfile

BF16_BASE = "zai-org/GLM-4-9B-0414"
CONVERT_SCRIPT = (
    "/tmp/claude-1000/-home-bheffernan-RazaAI/"
    "c0828d10-1025-4ad8-af93-7ecb55159670/scratchpad/"
    "llama.cpp/convert_hf_to_gguf.py"
)
QUANTIZE_BIN = "/opt/llama-vulkan/llama-b10217/llama-quantize"

def parse_args():
    p = argparse.ArgumentParser(description="Merge GLM adapter and export GGUF")
    p.add_argument("--checkpoint", required=True)
    p.add_argument("--base", default=BF16_BASE)
    p.add_argument("--merged-dir", default="RazaAI_gguf_glm_v1_merged")
    p.add_argument("--gguf-dir", default="RazaAI_gguf_glm_v1")
    p.add_argument("--quant", default="Q4_K_M")
    p.add_argument("--convert-script", default=CONVERT_SCRIPT)
    p.add_argument("--quantize-bin", default=QUANTIZE_BIN)
    p.add_argument("--keep-f16", action="store_true")
    p.add_argument("--ollama-model", default="raza-glm:9b-v1")
    p.add_argument("--modelfile", default=None,
                   help="Output Modelfile path (default: derived from --ollama-model)")
    return p.parse_args()

def main():
    args = parse_args()
    ckpt = Path(args.checkpoint)
    if not (ckpt / "adapter_config.json").exists():
        raise SystemExit(f"{ckpt} has no adapter_config.json")
    convert = Path(args.convert_script)
    if not convert.exists():
        raise SystemExit(f"convert script not found: {convert}")
    quantize = Path(args.quantize_bin)
    if not quantize.exists():
        raise SystemExit(f"llama-quantize not found: {quantize}")

    merged_dir = Path(args.merged_dir)
    gguf_dir = Path(args.gguf_dir)
    gguf_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading bf16 base {args.base} on CPU...")
    model = AutoModelForCausalLM.from_pretrained(
        args.base,
        dtype=torch.bfloat16,
        low_cpu_mem_usage=True,
        device_map="cpu",
    )

    print(f"Applying adapter {ckpt}...")
    model = PeftModel.from_pretrained(model, str(ckpt))
    model = model.merge_and_unload()

    print(f"Saving merged model to {merged_dir}...")
    model.save_pretrained(str(merged_dir))
    tokenizer = AutoTokenizer.from_pretrained(str(ckpt))
    tokenizer.save_pretrained(str(merged_dir))
    del model

    f16_path = gguf_dir / "raza-glm-9b-0414-f16.gguf"
    print(f"Converting to f16 GGUF: {f16_path}")
    subprocess.run(
        [
            sys.executable,
            str(convert),
            str(merged_dir),
            "--outfile",
            str(f16_path),
            "--outtype",
            "f16",
        ],
        check=True,
    )

    quant_path = gguf_dir / f"raza-glm-9b-0414.{args.quant}.gguf"
    print(f"Quantizing to {args.quant}: {quant_path}")
    subprocess.run(
        [str(quantize), str(f16_path), str(quant_path), args.quant],
        check=True,
    )

    if not args.keep_f16:
        f16_path.unlink()
        print("Removed intermediate f16 GGUF")

    modelfile = Path(
        args.modelfile
        or "Modelfile." + args.ollama_model.replace(":", "-").replace("/", "-")
    )
    write_modelfile(quant_path, modelfile)

    print("\n" + "=" * 64)
    print("MERGE + GGUF EXPORT COMPLETE")
    print("=" * 64)
    print(f"Merged (safetensors): {merged_dir.resolve()}")
    print(f"GGUF:                 {quant_path.resolve()}")
    print(f"Modelfile:            {modelfile.resolve()}")
    print()
    print(f"ollama create {args.ollama_model} -f {modelfile}")
    print(f"ollama run {args.ollama_model}")
    print("=" * 64)

if __name__ == "__main__":
    main()
