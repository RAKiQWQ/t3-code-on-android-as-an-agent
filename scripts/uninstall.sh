#!/usr/bin/env bash
set -Eeuo pipefail
if [[ $# != 0 ]]; then printf 'Usage: bash scripts/uninstall.sh\n' >&2; exit 2; fi
[[ $(uname -s) == Linux && $(id -u) != 0 ]] || { printf 'Run as the ordinary Linux VM user.\n' >&2; exit 1; }
config_dir="$HOME/.config/android-local-agent"
launcher="$HOME/.local/bin/phone-agent"
systemctl --user disable --now android-local-agent-link.service
if [[ -f "$launcher" ]] && grep -qF 'Maintain wireless ADB and phone-loopback access' "$launcher"; then
  python3 "$launcher" cleanup || printf 'ADB cleanup failed. After reconnecting, run: python3 src/phone_agent.py cleanup\n' >&2
  rm -- "$launcher"
fi
rm -f -- "$HOME/.config/systemd/user/android-local-agent-link.service" \
  "$HOME/.config/systemd/user/t3code.service.d/android-local-agent.conf"
systemctl --user daemon-reload
sdk_adb="$HOME/Android/Sdk/platform-tools/adb"
if [[ -f "$config_dir/sdk-adb-link" && -L "$sdk_adb" ]] && \
   [[ $(readlink "$sdk_adb") == "$(cat "$config_dir/sdk-adb-link")" ]]; then
  rm -- "$sdk_adb" "$config_dir/sdk-adb-link"
fi
printf '%s\n' 'Connection integration removed. Config, upstream tools, accounts and projects retained.'
