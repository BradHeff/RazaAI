#!/usr/bin/env bash
# Apply the Ollama memory settings for a Jetson Orin Nano 8 GB.
set -euo pipefail
if [[ "$EUID" -ne 0 ]]; then
  echo 'Run with sudo: sudo deploy/jetson-headless.sh' >&2; exit 1
fi
if [[ "$(uname -m)" != aarch64 || ! -f /etc/nv_tegra_release ]]; then
  echo 'This script requires an NVIDIA Jetson running JetPack.' >&2; exit 1
fi
source_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
install -d /etc/systemd/system/ollama.service.d
install -m 644 "$source_dir/ollama-override.conf" /etc/systemd/system/ollama.service.d/razaai-8g.conf
systemctl daemon-reload
systemctl restart ollama
printf 'Ollama is configured for one resident model.\n'
printf 'As your normal user, run: razaai-8g\n'
printf 'Optional console boot: sudo systemctl set-default multi-user.target\n'
