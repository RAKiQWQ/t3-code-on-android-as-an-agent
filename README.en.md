# Android Local Agent

[中文](README.md)

Run an agent inside a phone and connect it back to that same phone using the system Linux Terminal, T3 Code, Codex CLI, and Google's official Android CLI / SKILL. No dedicated agent app, Android root, or custom skill is required. Reuse subscription sign-in supported by the CLI. Programs and tools run on the phone; model inference uses cloud services.

This repository supplies only the wireless ADB connection and two phone-loopback endpoints: `3773` for T3 and `1455` for the Codex browser login callback. Terminal's built-in port discovery failed during testing, so one user service maintains the connection and forwarding.

## Install

The phone must provide Linux Terminal, wireless debugging must be enabled, and the VM must be able to reach the selected model service. Run these commands as the ordinary user inside the phone's Debian ARM64 VM. `sudo` grants VM administration only.

### 1. Install existing tools

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl adb python3 iproute2
curl -fsSL https://t3.codes/install.sh | sh
curl -fsSL https://chatgpt.com/codex/install.sh | sh
curl -fsSL https://dl.google.com/android/cli/latest/linux_arm64/install.sh | bash
export PATH="$HOME/.local/bin:$PATH"
mkdir -p "$HOME/.t3"
```

These installers fetch current upstream versions. Installation and account documentation: [T3](https://github.com/pingdotgg/t3code/blob/main/docs/user/install.md), [Codex](https://learn.chatgpt.com/docs/codex/cli), [Android CLI](https://developer.android.com/cli).

### 2. Install the connection layer and official skill

Add or update these settings in `~/.t3/service.env`, preserving other settings:

```dotenv
T3CODE_HOST=127.0.0.1
T3CODE_PORT=3773
```

Extract this repository into the VM, then run from its root:

```bash
t3 service install
bash install.sh
export ANDROID_HOME="$HOME/Android/Sdk"
export ANDROID_SDK_ROOT="$ANDROID_HOME"
android init
```

`android init` installs the official `android-cli` skill. Confirm Codex can read `~/.codex/skills/android-cli/SKILL.md`. The connection layer supplies T3's SDK environment and adds a link to the existing `adb` in the SDK directory if needed.

### 3. Pair, connect, and sign in

Open Developer options → Wireless debugging → Pair device with pairing code. Replace `12345` with the **pairing port**, then enter the pairing code at the terminal prompt:

```bash
phone-agent pair 12345
```

Return to the main wireless debugging page. Replace `54321` with its **connection port**:

```bash
phone-agent connect 54321
t3 service restart
codex login
t3 pair
```

Open the authorization link from `codex login` and the pairing link from `t3 pair` in the phone's browser. The everyday address is `http://127.0.0.1:3773/`. Pair only trusted environments; keep pairing links and ADB private keys private.

The VM gateway is the default phone address. To use another reachable address, add `--host PHONE_ADDRESS` to `pair` / `connect`. The only settings are `adb_host` and `adb_port`, stored in `~/.config/android-local-agent/config.json`.

### 4. Use

In T3, select the signed-in Codex provider and a working directory inside the VM. Start with:

> Use the official android-cli skill to read the current phone screen. Describe it without clicking.

## Maintenance

```bash
phone-agent connect 54321  # Replace with the new connection port when it changes
t3 service status
systemctl --user status android-local-agent-link
journalctl --user -u android-local-agent-link -n 30
bash scripts/uninstall.sh
```

Uninstall preserves connection settings, upstream tools, accounts, and working directories. The installer stops if it finds an earlier connection controller; disable and archive that controller first.

## Evidence

The original deployment used a Pixel 9a, GrapheneOS `2026102100` / Android 17, Debian 13 ARM64, T3 `0.1.2`, Codex `0.164.0`, and Android CLI `1.1.16717390`. Codex login, T3 browser pairing, same-phone ADB, and Android CLI screenshots succeeded. After a VM restart, services recovered and the phone's T3 endpoint returned HTTP 200. In subsequent hands-on testing, the user confirmed that this setup can control the phone to complete most tasks.

## Limitations

- Device testing covers the environment above and Codex. Other devices, ROMs, and providers such as Claude Code / OpenCode require separate verification.
- The main current issue is the system killing Terminal in the background, interrupting continued agent operation. Reliability during screen lock, extended background operation, and recovery after network changes still needs further verification.
- This repository's minimal installer has not been tested in a fresh phone VM. Neither local automated checks nor remote CI can replace device acceptance.
- Services run only while the VM runs. Update the wireless debugging connection port with `connect` when it changes.
- Do not enable `3773` / `1455` simultaneously in Terminal's Port control. The scheme depends on adbd supporting loopback listeners; verify the phone's listening addresses on other versions.

## Check and package

Python 3.10+ standard library only. Loopback forwarding requests `tcp:localhost:PORT` through the existing paired ADB transport and checks complete protocol responses. It does not fall back to all-interface listeners. See the [ADB implementation](https://android.googlesource.com/platform/packages/modules/adb/+/refs/heads/main/socket_spec.cpp).

```bash
python3 -m unittest discover -s tests -v
bash -n install.sh
bash -n scripts/uninstall.sh
bash install.sh --dry-run
python3 scripts/check_public.py
python3 scripts/package.py
```

Packaging produces the source-only `dist/android-local-agent-v0.1.0.zip` and SHA-256 checksums. This repository's code and documentation use [MIT](LICENSE). Third-party tools and official skills are installed from upstream and retain their own licenses and service terms.
