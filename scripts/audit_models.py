"""Model reference audit."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

IGNORE_DIRS = {
    ".git",
    "__pycache__",
    "evals",
}

IGNORE_FILES = {
    "CHANGELOG.md",
}

IGNORE_PREFIXES = ("README",)

DEPRECATED = (
    "raza-coder:7b",
    "raza-coder-3b",
)
DEPLOYMENT_PATHS = [
    "app",
    "config",
    "deploy",
    "runtime",
]
TRAINING_PATHS = [
    "training",
    "scripts/train",
    "data/coder_traces",
]
HISTORICAL_PATHS = [
    "tests",
    "docs",
    "README",
    "CHANGELOG",
]
active = []
historical = []

for p in ROOT.rglob("*"):
    if not p.is_file():
        continue
    if any(part in IGNORE_DIRS for part in p.parts):
        continue
    if p.name in IGNORE_FILES or p.name.startswith(IGNORE_PREFIXES):
        historical.append(str(p))
        continue

    try:
        text = p.read_text(errors="ignore")
    except Exception:
        continue

    if any(token in text for token in DEPRECATED):
        if p.parts[0] in {"docs", "training", "tests"}:
            historical.append(str(p))
        else:
            active.append(str(p))

print("RazaAI Model Audit")
print("==================")
print()

print("ACTIVE RUNTIME REFERENCES")
print("------------------------")
if active:
    for item in active:
        print(item)
else:
    print("PASS: no active deprecated model references")

print()
print("HISTORICAL REFERENCES")
print("---------------------")
if historical:
    for item in historical:
        print(item)
else:
    print("None")

print()
if active:
    raise SystemExit(1)

print("MODEL AUDIT PASSED")
