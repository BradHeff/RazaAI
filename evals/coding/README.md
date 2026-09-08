# Coding evaluation

The harness gives a model small projects and checks the resulting files and tests. It covers adding a function, editing an existing definition, renaming across files, repairing a failing test, adding a CLI flag, keeping changes within scope, validation, and a Node task when Node is installed.

```bash
.venv/bin/python -m scripts.coding_eval --list
.venv/bin/python -m scripts.coding_eval --model razaai-coder --runs 2
RAZAAI_PROFILE=8g .venv/bin/python -m scripts.coding_eval --model razaai-8g-coder --runs 2
```

Results are local CSV and Markdown files under `evals/coding/results/`. A stable pass means a task passed in every run. First-plan success measures whether the planner needed a retry. The report also records verification, elapsed time and tokens.

A rollback means the proposed code failed project checks. A verification pass followed by a checker failure means the change missed a requirement that the project's own tests did not cover. Keep both outcomes visible when comparing models.

Each task in `tasks.py` defines a setup function, request and on-disk checker. The reference clients prove the checkers can accept correct changes and reject specific mistakes; they are test fixtures, not model benchmarks.

Use repeated results on the target hardware when selecting a model. Keep private project content out of shared reports.
