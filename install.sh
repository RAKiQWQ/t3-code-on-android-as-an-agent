#!/usr/bin/env bash
set -Eeuo pipefail
project_dir=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
if [[ $# == 1 && $1 == --dry-run ]]; then
  printf '%s\n' 'Install phone-agent, a two-key config, ADB SDK link and user service integration.' \
    'Requires Linux, Python >=3.10, adb, ip and a T3 user service configured on 127.0.0.1:3773.' \
    'Pairing, provider login and official Android CLI skill initialization are manual.'
  exit 0
fi
if [[ $# != 0 ]]; then printf 'Usage: bash install.sh [--dry-run]\n' >&2; exit 2; fi
[[ $(uname -s) == Linux && $(id -u) != 0 ]] || { printf 'Run as the ordinary Android Linux VM user.\n' >&2; exit 1; }
for tool in python3 adb ip systemctl t3; do
  command -v "$tool" >/dev/null || { printf 'Missing prerequisite: %s\n' "$tool" >&2; exit 1; }
done
python3 -c 'import sys; assert sys.version_info >= (3,10), "Python >=3.10 required"'
systemctl --user show-environment >/dev/null
[[ $(systemctl --user show t3code.service -p LoadState --value) == loaded ]] || {
  printf 'Configure T3 on loopback and run: t3 service install\n' >&2; exit 1;
}
python3 - <<'PY'
from pathlib import Path
settings = dict(line.strip().split('=', 1) for line in (Path.home() / '.t3/service.env').read_text().splitlines()
                if '=' in line and not line.lstrip().startswith('#'))
if settings.get('T3CODE_HOST') != '127.0.0.1' or settings.get('T3CODE_PORT') != '3773':
    raise SystemExit('Set T3CODE_HOST=127.0.0.1 and T3CODE_PORT=3773 in ~/.t3/service.env first.')
PY
launcher="$HOME/.local/bin/phone-agent"
if [[ -e "$HOME/.config/systemd/user/phone-link.service" ]] || \
   systemctl --user is-active --quiet phone-link.service || \
   { [[ -e "$launcher" ]] && ! grep -qF 'Maintain wireless ADB and phone-loopback access' "$launcher"; }; then
  printf 'An earlier connection controller exists; stop and archive it before installing.\n' >&2; exit 1
fi
config_dir="$HOME/.config/android-local-agent"
install -d -m 700 "$config_dir"
if [[ -f "$config_dir/config.json" ]]; then
  python3 - "$project_dir/src" "$config_dir/config.json" <<'PY'
import sys
from pathlib import Path
sys.dont_write_bytecode = True
sys.path.insert(0, sys.argv[1])
from phone_agent import read_config
read_config(Path(sys.argv[2]))
PY
else
  (umask 077; printf '{"adb_host":"auto","adb_port":null}\n' > "$config_dir/config.json")
fi
install -d -m 755 "$HOME/.local/bin" "$HOME/Android/Sdk/platform-tools" \
  "$HOME/.config/systemd/user/t3code.service.d"
install -m 755 "$project_dir/src/phone_agent.py" "$launcher"
sdk_adb="$HOME/Android/Sdk/platform-tools/adb"
if [[ ! -e "$sdk_adb" && ! -L "$sdk_adb" ]]; then
  ln -s "$(command -v adb)" "$sdk_adb"
  (umask 077; readlink "$sdk_adb" > "$config_dir/sdk-adb-link")
fi
install -m 644 "$project_dir/systemd/android-local-agent-link.service" "$HOME/.config/systemd/user/"
install -m 644 "$project_dir/systemd/t3code-android-local-agent.conf" \
  "$HOME/.config/systemd/user/t3code.service.d/android-local-agent.conf"
systemctl --user daemon-reload
systemctl --user enable --now android-local-agent-link.service
printf '%s\n' 'Installed. Pair and connect, then run: t3 service restart'
