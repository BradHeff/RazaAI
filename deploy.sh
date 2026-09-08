#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
profile="${1:-standard}"
case "$profile" in
  standard|8g) ;;
  -h|--help) echo 'Usage: ./deploy.sh [standard|8g] [--skip-models]'; exit 0 ;;
  *) echo 'Choose standard (RTX 4080+) or 8g (Jetson Orin Nano 8 GB).' >&2; exit 2 ;;
esac
if [[ $# -gt 2 || ( $# -eq 2 && "$2" != --skip-models ) ]]; then
  echo 'Usage: ./deploy.sh [standard|8g] [--skip-models]' >&2
  exit 2
fi
cd "$project_root"
python3 -c 'import sys; sys.exit("Python 3.10 or later is required" if sys.version_info < (3, 10) else 0)'
python3 -m scripts.upgrade_cleanup
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
# Resolve binary wheels on the target architecture, never from another device's freeze.
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pip check
mkdir -p "$HOME/.local/bin"
for launcher in razaai razaai-8g raza-code; do
  ln -sfn "$project_root/$launcher" "$HOME/.local/bin/$launcher"
done
ln -sfn "$project_root/bin/raza" "$HOME/.local/bin/raza"
if [ "${2:-}" != --skip-models ]; then
  .venv/bin/python -m app.launcher --profile "$profile" models
fi
printf 'Installed. Add ~/.local/bin to PATH if needed.\n'
if [ "$profile" = 8g ]; then
  printf 'Run: ./razaai-8g\nJetson setup: docs/ROAD_SETUP.md\n'
else
  printf 'Run: ./razaai\n'
fi
