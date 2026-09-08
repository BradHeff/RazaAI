#!/usr/bin/env bash
# Copy project data and profile state into a local backup directory.
set -euo pipefail
cd "$(dirname "$0")/.."
exec python3 -m scripts.backup "$@"
