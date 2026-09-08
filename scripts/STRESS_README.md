# Stress tests

The stress scripts exercise real agents and Ollama. Results stay local under `evals/stress/results/`.

```bash
.venv/bin/python -m scripts.stress_session --cycles 3 --conversation-only
.venv/bin/python -m scripts.stress_session --cycles 5 --swap-models
```

Session tests cover conversation, identity, coding proposals, approval, undo, checkpoints and memory. They use temporary state and workspaces. Add `--keep-workspace` when you need to inspect a failure.

Service tests send concurrent requests to an already running service:

```bash
.venv/bin/python -m scripts.stress_service --url http://127.0.0.1:8420 --sessions 4 --rounds 5
```

Use the script's `--help` for authentication options. The HTTP service is workstation-only. Test Jetson through its terminal and session runner.

Application violations include broken stream framing, crossed sessions, lost state and failed rollback. Model failures include incorrect plans that the application catches and rolls back. Report these separately.

Watch available memory, swap growth, prompt size, latency and failures across cycles. Measure Jetson performance on the Jetson itself. A workstation run checks behavior but cannot establish the smaller device's memory use or response time.
