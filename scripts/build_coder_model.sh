#!/usr/bin/env bash
# Build the legacy RazaAI coder aliases for existing installations.
set -euo pipefail
cd "$(dirname "$0")/.."
MODE="${2:-current}"

if [ "$MODE" = "legacy" ]; then
  TAG="${1:-raza-coder:3b-v1}"
  BASE="hf.co/ICEPVP8977/Uncensored_Qwen2.5_Coder_3B:F16"
  echo "[1/4] pulling base ($BASE) — F16, ~6 GB download, needs ~7 GB free disk"
  ollama pull "$BASE"
  echo "[2/4] creating $TAG quantized to q4_K_M"
  ollama create "$TAG" --quantize q4_K_M -f Modelfile.raza-coder-3b
else
  TAG="${1:-raza-coder:qwen3-4b-v1}"
  echo "[1/4] creating $TAG (Modelfile pulls the already-quantized Q4_K_M GGUF)"
  ollama create "$TAG" -f Modelfile.raza-coder-3b-v2
fi
echo "[3/4] verifying"
ollama show "$TAG" | grep -E "quantization|num_ctx|num_batch|capabilities" -A3 | head -20
echo "[4/4] smoke test (identity + JSON discipline)"
ollama run "$TAG" "who made you? answer in one line" | head -3
ollama run "$TAG" 'Return only JSON: {"files":[],"summary":"smoke"}' | head -3
echo
echo "Done. Baseline then candidate:"
echo "  python3 -m scripts.coding_eval --model raza-edge:4b-v3 --runs 2"
echo "  python3 -m scripts.coding_eval --model $TAG --runs 2"
echo "Adopt for coding sessions only if it wins on stable pass:  export RAZAAI_CODE_MODEL=$TAG"
