# Development

## Runtime

The two launchers call `app.launcher`, which selects a profile before importing application configuration. `app.profiles` owns the defaults. `app.config` validates environment overrides. The Ollama client applies context and batch limits to requests; Python budgets evidence and history to the same context window.

Use Python 3.10 or later. The application environment contains retrieval, SSH/WinRM, document and terminal libraries. GPU inference runs in Ollama, so application installation does not install CUDA or PyTorch.

```bash
./deploy.sh standard --skip-models
.venv/bin/python -m tests.run_fast
```

Run entry points through `.venv/bin/python` when working directly with modules. `python -m app.main` uses the standard profile unless `RAZAAI_PROFILE=8g` is set. `python -m app.server` is workstation-only. The named launchers select separate state locations and default to the terminal. `razaai code [directory]` and `razaai-8g code [directory]` enter the coding workspace. Browser serving is restricted to the standard profile through `razaai web`; the 8 GB launcher does not expose browser or token commands.

## Validation

```bash
.venv/bin/python -m tests.run_fast
.venv/bin/python -m tests.run_core
.venv/bin/python -m tests.run_integration
.venv/bin/python -m tests.run_offline
```

The offline and tier runners build an isolated synthetic knowledge corpus and index, then launch each test module separately. They do not use private field notes or the operator's memory. The first index build needs the embedding-model download; cache it before running without internet access.

Model tests are separate:

```bash
RAZAAI_PROFILE=standard .venv/bin/python -m scripts.coding_eval --model razaai-coder --runs 2
RAZAAI_PROFILE=8g .venv/bin/python -m scripts.coding_eval --model razaai-8g-coder --runs 2
RAZAAI_PROFILE=8g .venv/bin/python -m tests.run_device
```

Run device checks on the target hardware. Before calling a Jetson release validated, test cold startup, several long conversations, conversation/coder switching, approval and rollback, and offline operation. Record available RAM, swap growth, GPU use and response times. Use `tegrastats` on Jetson and `nvidia-smi` on a workstation.

Profile and server regression tests cover separate defaults, bounded Jetson settings, model overrides, overlapping sessions, request parsing and warmup options. A passing test suite establishes the exercised behavior, not a guarantee of model answer quality or Jetson memory fit.

Validation on 8 September 2026: all 158 offline test modules passed from the public source export on Linux with Python 3.13, after a fresh dependency installation. Both model profiles completed real propose, approve, verify and undo cycles on an RTX 4080. The 8 GB profile also completed that cycle through the terminal UI. Browser checks covered authentication, interrupted streams, duplicate submissions and mobile layout. Physical Jetson validation remains outstanding.

## Personality and reasoning

See [personality](PERSONALITY.md) for the shared mission, prompt integration and native thinking controls. Persona changes do not alter model weights or permission checks.

## Coding controls

A model proposes file operations. Python validates paths, patch anchors, requested file scope, syntax and retained symbols. The user reviews a diff before `/approve`. The application snapshots affected files, applies changes, runs project checks, and restores the snapshot if verification fails.

Transactions and one level of undo survive a restart. `/checkpoint` creates a commit on a `raza/` branch. The general command runner cannot perform arbitrary Git writes.

Verification runs in a temporary project copy. If available, bubblewrap adds operating-system isolation. The report names the isolation level that worked. Without bubblewrap, project code still runs with the operator's OS permissions; a temporary copy is not a security sandbox. Do not execute unfamiliar projects merely because the model suggested a test.

Self-modifying tools require `RAZAAI_SELFOPS=1`. They are disabled by default. Infrastructure tools require explicitly enabled inventory entries and environment credentials.

## HTTP API

The workstation browser and `bin/raza` use the same API. The Jetson profile has no HTTP service. All operators who share a token share authority; session IDs separate conversations, not accounts.

| Method and path | Response |
| --- | --- |
| `GET /` | Browser interface |
| `GET /healthz` | Health JSON; 503 when degraded; no token required |
| `POST /v1/chat` | NDJSON deltas followed by a final result or error |
| `GET /v1/sessions` | Retained session IDs and turn counts |
| `DELETE /v1/sessions/<id>` | Whether an idle session was removed |
| `GET /v1/doctor` | Detailed runtime diagnostics |

Authenticated requests use `Authorization: Bearer <token>`. A chat body is:

```json
{"session": "example", "message": "Explain a VLAN"}
```

Responses use HTTP/1.1 chunked transfer encoding:

```json
{"delta": "A VLAN "}
{"done": true, "content": "A VLAN separates a layer-2 network.", "session": "example"}
```

Clients must use the final `content`, since response validation can revise streamed text. An `error` record is terminal. Treat end-of-stream without either terminal record as a failed request. `thinking_delta` records carry model reasoning separately from the answer.

The service serializes model turns, bounds retained sessions and client threads, rejects oversized or ambiguous request bodies, and leaves the health endpoint available while Ollama is down. Use TLS or an SSH tunnel for access across untrusted networks.

## Dependencies and releases

Runtime requirements resolve on the target architecture. A local `pip freeze` is a record of one environment, not a portable Jetson lock. Fine-tuning experiments, datasets and model exports are maintained outside the source tree. No trainer is bundled. The optional training job API requires `RAZAAI_TRAINER_SCRIPT` to point to a compatible Python trainer, `RAZAAI_ALLOW_MODEL_TRAINING=1`, and user approval. Set `RAZAAI_TRAINER_PYTHON` when that trainer uses a separate environment. Its command-line arguments are defined in `app/selfops/training.py`.

```bash
scripts/package_release.sh
```

This builds `dist/RazaAI-v<version>.zip` from nonignored public working-tree files. It includes current edits and new source files, but excludes Git history, local credentials, runtime records, training datasets, models and private reference material. Check the archive before sharing it.

Ignoring a file does not remove older copies from Git history. The local repository previously tracked a token and private records. Publish a new repository initialized from the clean source export, or separately review and remove sensitive history before pushing an existing repository. Do not publish the old history as part of the portfolio.

## Maintenance scripts

| Script | Purpose |
| --- | --- |
| `ingest_knowledge.py`, `search_knowledge.py` | Index and search reference documents |
| `learning_loop.py`, `promote_incident_knowledge.py`, `review_knowledge_feedback.py` | Review and promote incident knowledge |
| `coding_eval.py`, `capability_eval.py` | Evaluate a running model |
| `stress_session.py`, `stress_service.py` | Exercise terminal sessions and the workstation API |
| `backup.sh`, `backup.py` | Back up local runtime records |
| `install-service.sh` | Install the workstation browser service |
| `package_release.sh`, `package_release.py` | Export the public source archive |
| `upgrade_cleanup.py` | Remove a retired nested package during upgrades |

Run Python scripts with `.venv/bin/python -m scripts.<name>`. Evaluation and stress runners provide `--help`. See [stress testing](../scripts/STRESS_README.md) for the stress runners.

## Source layout and style

Keep runtime profile logic in `app/profiles.py`. Keep hardware-specific setup out of the agent. Add regression coverage for changes to authority, memory limits, session handling and file writes.

Write comments for a function's purpose or a constraint that is not obvious from the code. Put release history in the changelog. Keep private reports, screenshots used only during debugging, model outputs and scratch notes under ignored paths.
