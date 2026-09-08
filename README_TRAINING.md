# Training RazaAI models

Training is optional. The public runtime can download base models without a training environment. This guide describes the scripts retained for the Qwen3 4B edge model and GLM-4 9B workstation experiments.

## Keep training separate

Use a workstation with CUDA and a dedicated virtual environment. The Jetson 8 GB kit is an inference target. Model weights, adapters, datasets, logs and generated caches stay local.

```bash
python3 -m venv .venv-train
.venv-train/bin/python -m pip install -r requirements-training.txt
.venv-train/bin/python train_raza_glm.py --help
.venv-train/bin/python train_raza_v3.py --help
```

The training stack has different dependencies from the application. Check its compatibility with your Python, CUDA, GPU and base checkpoint before a full run. The runtime audit does not validate a new training run.

## Model lineage

The original edge fine-tune used `MassivDash/Qwen3-4B-heretic`, with the deployed Q4_K_M GGUF tagged `raza-edge:4b-v3`. The retained GLM workflow specializes GLM-4 9B 0414. The public `razaai-8g` setup instead downloads Qwen3-4B-Instruct-2507 so a new user can start without private model artifacts.

Train the Hugging Face checkpoint, retain the LoRA adapter, merge it, then export and quantize a new GGUF. Do not train a quantized GGUF directly. Record the base checkpoint revision, dataset hash, exact arguments, library versions and evaluation results with each local run.

`train_raza_glm.py` handles GLM training, `merge_glm_gguf.py` handles export, and `eval_glm_checkpoints.py` compares checkpoints. Use each script's `--help` for the implemented arguments. The original datasets are excluded from the public repository because they require a separate privacy and redistribution review.

## Data and evaluation

Use only data you have permission to train on. Remove credentials and private infrastructure details, deduplicate examples, and keep evaluation cases separate from training. Train for recurring model failures such as poor reasoning or response style. Fix application routing, evidence delivery and tool permissions in Python.

Coding plans must be valid operations in the application's schema. Test a corrected plan against the actual fixture before adding it to training. A small collection of nearly identical examples can teach a repetitive response rather than a general skill.

```bash
.venv/bin/python -m scripts.coding_eval --model <candidate-tag> --runs 2
.venv/bin/python -m tests.run_offline
```

Compare candidates on correctness, repeatability, memory demand and response time on the intended device. A model-level score does not prove application safety, and a workstation result does not establish Jetson performance.

## Use a trained model

Once your fine-tune exists in Ollama:

```bash
razaai models --from raza-glm:9b-v4
razaai-8g models --from raza-edge:4b-v3
```

A GGUF path can also be passed to `--from`. Check that the architecture's chat template is present and the result uses the intended quantization. Run `ollama show <tag>` and a direct model conversation before testing it through RazaAI.

The application continues to own identity facts, tool authorization, secret handling, memory and evidence. Fine-tuning does not grant execution authority. The MIT licence covers this source; base models and redistributed weights retain their own terms.
