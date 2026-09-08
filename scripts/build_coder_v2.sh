#!/usr/bin/env bash
# RazaAI-Coder v2: seed -> train -> GGUF -> Ollama -> measure. Run on the host (RTX 4080).
#   scripts/build_coder_v2.sh dry-run     # 0.5B base, proves the whole chain in minutes
#   scripts/build_coder_v2.sh train       # the real 7B run
#   scripts/build_coder_v2.sh measure     # eval + stress against raza-coder:3b-v1-v2
set -euo pipefail
cd "$(dirname "$0")/.."
mode="${1:-train}"

if [ ! -d .venv-train ]; then
  echo "[setup] dedicated training venv (.venv-train) — unsloth/trl pins must not touch the app venv"
  python3 -m venv .venv-train
  .venv-train/bin/pip install -q -U pip
  .venv-train/bin/pip install -q -U "unsloth[cu124-torch250] @ git+https://github.com/unslothai/unsloth.git" trl datasets transformers accelerate bitsandbytes 2>/dev/null \
    || .venv-train/bin/pip install -q -U unsloth trl datasets transformers accelerate bitsandbytes
fi
PY=.venv-train/bin/python

case "$mode" in
  dry-run)
    [ -f training/coder_v2_seed/coder_v2.jsonl ] || { echo "no seed: run export_coder_seed --autocorrect then --finalize"; exit 1; }
    $PY scripts/train_coder_v2.py --dry-run
    ollama run raza-coder:dryrun --think=false 'Return only JSON: {"files":[],"summary":"smoke"}' | head -3
    ;;
  train)
    n=$(grep -c . training/coder_v2_seed/coder_v2.jsonl 2>/dev/null || echo 0)
    echo "[seed] $n example(s)"
    [ "$n" -ge 1 ] || exit 1
    [ "$n" -lt 50 ] && echo "[warn] fewer than 50 examples: expect a narrow effect; keep collecting traces across stress runs"
    $PY scripts/train_coder_v2.py "${@:2}"
    ;;
  measure)
    python3 -m scripts.coding_eval --model raza-coder:3b-v1-v2 --runs 2
    RAZAAI_CODE_MODEL=raza-coder:3b-v1-v2 python3 -m scripts.stress_session --cycles 10
    echo "Compare with the v1 numbers in evals/coding/results and evals/stress/results; adopt only if both improve."
    ;;
  *) echo "usage: $0 dry-run|train|measure"; exit 64 ;;
esac
