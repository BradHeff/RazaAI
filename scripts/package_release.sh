#!/usr/bin/env bash
# Export public source without local state, private references or Git history.
set -euo pipefail
cd "$(dirname "$0")/.."
exec python3 -m scripts.package_release "$@"
