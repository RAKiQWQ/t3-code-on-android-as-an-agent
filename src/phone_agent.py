#!/usr/bin/env python3
"""Maintain wireless ADB and phone-loopback access to T3 and Codex login."""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import time

UNIT = "android-local-agent-link.service"
PORTS = (3773, 1455)


@dataclass(frozen=True)
class Config:
    adb_host: str = "auto"
    adb_port: int | None = None

    @classmethod
    def parse(cls, data: dict) -> Config:
        if not isinstance(data, dict) or set(data) - {"adb_host", "adb_port"}:
            raise ValueError("Config accepts only adb_host and adb_port")
        config = cls(**data)
        if not isinstance(config.adb_host, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]+", config.adb_host):
            raise ValueError("adb_host must be auto, an IP address, or a hostname")
        if config.adb_port is not None:
            if type(config.adb_port) is not int or not 1 <= config.adb_port <= 65535:
                raise ValueError("adb_port must be in 1..65535")
            if config.adb_port in PORTS:
                raise ValueError("Wireless debugging port conflicts with a managed listener")
        return config


def read_config(path: Path) -> Config:
    return Config.parse(json.loads(path.read_text(encoding="utf-8")))


def save_config(path: Path, config: Config) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(asdict(config), stream, indent=2)
            stream.write("\n")
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def run(*command: str) -> tuple[int, str]:
    result = subprocess.run(command, capture_output=True, text=True, timeout=10)
    return result.returncode, (result.stdout + result.stderr).strip()


def endpoint(config: Config) -> str:
    selected = config.adb_port
    if selected is None:
        raise RuntimeError("Run phone-agent connect CONNECTION_PORT")
    host = config.adb_host
    if host == "auto":
        code, output = run("ip", "-4", "route", "show", "default")
        match = re.search(r"\bvia\s+([0-9.]+)", output)
        if code or not match:
            raise RuntimeError("No IPv4 default gateway; use --host PHONE_ADDRESS")
        host = match.group(1)
    return (f"[{host}]" if ":" in host else host) + f":{selected}"


def adb(*arguments: str, device: str | None = None) -> tuple[int, str]:
    command = ["adb", "-H", "127.0.0.1", "-P", "5037"]
    if device:
        command += ["-s", device]
    return run(*command, *arguments)


def receive_exact(connection: socket.socket, count: int) -> bytes:
    result = bytearray()
    while len(result) < count:
        chunk = connection.recv(count - len(result))
        if not chunk:
            raise OSError("ADB closed an incomplete response")
        result.extend(chunk)
    return bytes(result)


def adb_status(connection: socket.socket) -> None:
    status = receive_exact(connection, 4)
    if status == b"FAIL":
        length = int(receive_exact(connection, 4), 16)
        raise OSError(receive_exact(connection, length).decode(errors="replace"))
    if status != b"OKAY":
        raise OSError("Unexpected ADB response")


def adb_request(connection: socket.socket, command: str) -> None:
    data = command.encode()
    if len(data) > 65535:
        raise ValueError("ADB request is too long")
    connection.sendall(f"{len(data):04x}".encode() + data)
    adb_status(connection)


def reverse_loopback(device: str, port: int, server_port: int = 5037) -> None:
    # adbd supports tcp:localhost:PORT, but the tested adb CLI rejects it.
    # Use the existing paired transport and check both service status frames.
    with socket.create_connection(("127.0.0.1", server_port), timeout=8) as connection:
        adb_request(connection, "host:transport:" + device)
        adb_request(connection, f"reverse:forward:tcp:localhost:{port};tcp:{port}")
        adb_status(connection)


def remove_mappings(device: str, ports=PORTS) -> None:
    code, output = adb("reverse", "--list", device=device)
    if code:
        raise RuntimeError("Cannot list ADB reverse mappings")
    for port in ports:
        spec = f"tcp:{port}"
        if any(line.split()[-2:] == [spec, spec] for line in output.splitlines()):
            code, _ = adb("reverse", "--remove", spec, device=device)
            if code:
                raise RuntimeError("Cannot remove a managed reverse mapping")


class Link:
    def __init__(self):
        self.device: str | None = None

    def cycle(self, config: Config) -> str:
        if config.adb_port is None:
            return "Run phone-agent pair PAIRING_PORT, then phone-agent connect CONNECTION_PORT"
        device = endpoint(config)
        code, output = adb("get-state", device=device)
        if code or output != "device":
            self.device = None
            adb("connect", device)
            code, output = adb("get-state", device=device)
        if code or output != "device":
            return "Wireless ADB unavailable; check pairing and the current connection port"
        code, output = adb("reverse", "--list", device=device)
        if code:
            raise RuntimeError("Cannot list ADB reverse mappings")
        for port in PORTS:
            spec = f"tcp:{port}"
            exists = any(line.split()[-2:] == [spec, spec] for line in output.splitlines())
            if exists and self.device == device:
                continue
            if exists:
                remove_mappings(device, (port,))
            reverse_loopback(device, port)
        self.device = device
        return "Phone-local link ready: http://127.0.0.1:3773/"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("run", help="Connection daemon (managed by systemd)")
    commands.add_parser("cleanup", help="Remove managed mappings after stopping the daemon")
    for name in ("pair", "connect"):
        command = commands.add_parser(name)
        command.add_argument("port", type=int)
        command.add_argument("--host", help="Phone address reachable from the VM; defaults to its gateway")
    args = parser.parse_args(argv)
    path = Path.home() / ".config/android-local-agent/config.json"
    config = read_config(path)
    if args.command in ("pair", "connect"):
        selected = Config.parse({"adb_host": args.host or config.adb_host, "adb_port": args.port})
        if args.command == "pair":
            code = subprocess.call(["adb", "-H", "127.0.0.1", "-P", "5037", "pair", endpoint(selected)])
            if code:
                return code
            save_config(path, Config(selected.adb_host, config.adb_port))
        else:
            save_config(path, selected)
            subprocess.run(["systemctl", "--user", "restart", UNIT], check=True)
        return 0
    if args.command == "cleanup":
        code, state = run("systemctl", "--user", "is-active", UNIT)
        if code == 0 or state in {"activating", "deactivating", "reloading"}:
            raise RuntimeError("Stop the connection service before cleanup")
        if config.adb_port is not None:
            remove_mappings(endpoint(config))
        return 0
    link, previous = Link(), None
    while True:
        try:
            message = link.cycle(read_config(path))
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
            link.device = None
            message = "Link error: " + str(error)
        if message != previous:
            print(message, flush=True)
            previous = message
        time.sleep(12)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print("phone-agent:", str(error), file=sys.stderr)
        raise SystemExit(1)
