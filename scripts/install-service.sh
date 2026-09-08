#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
profile="${1:-standard}"
case "$profile" in
  standard) launcher=razaai; memory=4G ;;
  8g) echo "The Jetson profile is terminal-only. Run razaai-8g over SSH; use tmux to retain the terminal session." >&2; exit 2 ;;
  *) echo 'Usage: scripts/install-service.sh [standard]' >&2; exit 2 ;;
esac
# Reject paths that need extra systemd escaping.
if [[ "$project_root" =~ [[:space:]%\\\"] ]]; then
  echo 'Install the service from a checkout path without spaces, quotes, backslashes or percent signs.' >&2
  exit 2
fi
mkdir -p "$HOME/.config/systemd/user" "$HOME/.config/$launcher"
[ -e "$HOME/.config/$launcher/server.env" ] || install -m 600 "$project_root/deploy/razaai-server.env" "$HOME/.config/$launcher/server.env"
python3 - "$project_root" "$launcher" "$memory" <<'PY'
from pathlib import Path
import sys
root, launcher, memory = sys.argv[1:]
text = (Path(root) / 'deploy/razaai-server.service').read_text()
text = text.replace('@PROJECT_ROOT@', root).replace('@LAUNCHER@', launcher).replace('@MEMORY_MAX@', memory)
(Path.home() / '.config/systemd/user' / f'{launcher}.service').write_text(text)
learning = (Path(root) / 'deploy/razaai-learning.service').read_text()
learning = learning.replace('@PROJECT_ROOT@', root).replace('@LAUNCHER@', launcher)
(Path.home() / '.config/systemd/user' / f'{launcher}-learning.service').write_text(learning)
timer = (Path(root) / 'deploy/razaai-learning.timer').read_text()
(Path.home() / '.config/systemd/user' / f'{launcher}-learning.timer').write_text(timer)
PY
systemctl --user daemon-reload
systemctl --user enable --now "$launcher.service"
printf 'Installed %s.service. Logs: journalctl --user -u %s -f\n' "$launcher" "$launcher"
