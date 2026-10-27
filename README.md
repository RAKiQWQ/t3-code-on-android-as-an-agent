# Android Local Agent

[English](README.en.md)

用系统自带 Linux Terminal、T3 Code、Codex CLI 和 Google 官方 Android CLI / SKILL，在手机内运行 Agent 并连接回同一部手机。无需专用 Agent App、Android Root 或自写 SKILL，沿用 CLI 支持的订阅登录。程序和工具运行在手机内，模型推理调用云端服务。

本仓库只补上同机无线 ADB 连接与两个手机回环入口：`3773` 用于 T3，`1455` 用于 Codex 浏览器登录回调。实测 Terminal 原生端口发现曾失效，因此由一个用户服务维护连接和转发。

## 安装

需要手机系统提供 Linux Terminal、已启用无线调试，且 VM 能访问所选模型服务。以下命令均在手机的 Debian ARM64 VM 中以普通用户执行；`sudo` 仅用于 VM 内管理。

### 1. 安装现成工具

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl adb python3 iproute2
curl -fsSL https://t3.codes/install.sh | sh
curl -fsSL https://chatgpt.com/codex/install.sh | sh
curl -fsSL https://dl.google.com/android/cli/latest/linux_arm64/install.sh | bash
export PATH="$HOME/.local/bin:$PATH"
mkdir -p "$HOME/.t3"
```

安装脚本获取上游当前版本。安装与账号说明：[T3](https://github.com/pingdotgg/t3code/blob/main/docs/user/install.md)、[Codex](https://learn.chatgpt.com/docs/codex/cli)、[Android CLI](https://developer.android.com/cli)。

### 2. 安装连接层与官方技能

在 `~/.t3/service.env` 中添加或更新下列设置，保留已有其他设置：

```dotenv
T3CODE_HOST=127.0.0.1
T3CODE_PORT=3773
```

将本仓库解压到 VM，在仓库根目录执行：

```bash
t3 service install
bash install.sh
export ANDROID_HOME="$HOME/Android/Sdk"
export ANDROID_SDK_ROOT="$ANDROID_HOME"
android init
```

`android init` 安装官方 `android-cli` 技能；确认 Codex 能读取 `~/.codex/skills/android-cli/SKILL.md`。连接层会为 T3 设置 SDK 路径，并在 SDK 中补上现有 `adb` 的链接。

### 3. 配对、连接、登录

在手机“开发者选项 → 无线调试 → 使用配对码配对设备”中查看**配对端口**，将 `12345` 替换为实际值，按终端提示输入配对码：

```bash
phone-agent pair 12345
```

回到无线调试主页面，将 `54321` 替换为该页的**连接端口**：

```bash
phone-agent connect 54321
t3 service restart
codex login
t3 pair
```

分别在手机浏览器打开 `codex login` 的授权链接和 `t3 pair` 的配对链接。日常入口是 `http://127.0.0.1:3773/`。只配对可信环境，不公开配对链接或 ADB 私钥。

默认通过 VM 网关连接手机；如需指定其他可达地址，给 `pair` / `connect` 加上 `--host 手机地址`。配置仅有 `adb_host`、`adb_port` 两项，保存在 `~/.config/android-local-agent/config.json`。

### 4. 使用

在 T3 中选择已登录的 Codex 和 VM 内的工作目录，先发送：

> 使用官方 android-cli 技能读取当前手机界面，只描述内容，不要点击。

## 维护

```bash
phone-agent connect 54321  # 连接端口变化后，替换为新端口
t3 service status
systemctl --user status android-local-agent-link
journalctl --user -u android-local-agent-link -n 30
bash scripts/uninstall.sh
```

卸载保留连接配置、上游工具、账号和工作目录。安装器遇到早期连接控制器会退出，需先停用并归档旧控制器。

## 实践依据

原始部署使用 Pixel 9a、GrapheneOS `2026102100` / Android 17、Debian 13 ARM64，以及 T3 `0.1.2`、Codex `0.164.0`、Android CLI `1.1.16717390`。已完成 Codex 登录、T3 浏览器配对、同机 ADB 和 Android CLI 截图；重启 VM 后服务恢复，手机 T3 入口返回 HTTP 200。用户后续实测已能通过该方案操控手机完成大部分任务。

## 局限性

- 实测范围限于上述设备、系统和 Codex；其他设备、ROM、Claude Code / OpenCode 等需分别验证。
- 当前主要问题集中在 Terminal 在后台被系统终止，影响 Agent 持续运行。锁屏、长期后台和换网恢复的稳定性仍需进一步验证。
- 本仓库精简安装器尚未在全新手机 VM 中实装验收；本地自动检查和远端 CI 均不能替代真机验收。
- 服务随 VM 运行，不能在 VM 停止后继续执行。无线调试连接端口变化后需手动 `connect`。
- Terminal 的 Port control 不应同时开启 `3773` / `1455`；本方案依赖 adbd 支持回环监听。其他版本需核对手机监听地址。

## 检查与发布

仅使用 Python 3.10+ 标准库。回环转发通过已有 ADB 配对连接请求 `tcp:localhost:端口`，检查完整协议响应；不退回全网卡监听。参考 [ADB 实现](https://android.googlesource.com/platform/packages/modules/adb/+/refs/heads/main/socket_spec.cpp)。

```bash
python3 -m unittest discover -s tests -v
bash -n install.sh
bash -n scripts/uninstall.sh
bash install.sh --dry-run
python3 scripts/check_public.py
python3 scripts/package.py
```

打包生成 `dist/android-local-agent-v0.1.0.zip` 与 SHA-256 清单，只含源码。自有代码与文档采用 [MIT](LICENSE)；第三方工具和官方技能从上游安装，适用各自许可与服务条款。
