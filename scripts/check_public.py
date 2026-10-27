#!/usr/bin/env python3
"""Check the release allowlist and reject obvious credential material."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
RELEASE_FILES = {
    "README.md", "README.en.md", "LICENSE", ".gitignore", ".gitattributes", "install.sh",
    "src/phone_agent.py", "tests/test_phone_agent.py", ".github/workflows/check.yml",
    "systemd/android-local-agent-link.service", "systemd/t3code-android-local-agent.conf",
    "scripts/uninstall.sh", "scripts/check_public.py", "scripts/package.py",
}
IGNORED = {".git", "dist", "__pycache__", ".venv"}
FORBIDDEN_NAMES = {"auth.json", ".env", "phone-access", "adbkey", "id_rsa", "id_ed25519"}
PATTERNS = [
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(rb"\bsk-[A-Za-z0-9_-]{24,}\b"),
    re.compile(rb"\beyJ[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}"),
    re.compile(rb"[A-Za-z]:[\\/]Users[\\/][A-Za-z0-9_.-]+[\\/]"),
]


def public_files() -> list[Path]:
    result = []
    for path in sorted(ROOT.rglob("*")):
        relative = path.relative_to(ROOT)
        if any(part in IGNORED for part in relative.parts) or path.is_dir():
            continue
        if path.is_symlink():
            raise ValueError("Release symlink is not allowed: " + str(relative))
        if path.name in FORBIDDEN_NAMES:
            raise ValueError("Private filename: " + str(relative))
        if relative.as_posix() not in RELEASE_FILES:
            raise ValueError("Unexpected release file: " + str(relative))
        if path.suffix.lower() in {".png", ".jpg", ".zip", ".log", ".pem", ".key", ".exe"}:
            raise ValueError("Non-source file in release: " + str(relative))
        data = path.read_bytes()
        if b"\0" in data:
            raise ValueError("Binary content in release: " + str(relative))
        for pattern in PATTERNS:
            if pattern.search(data):
                raise ValueError("Possible credential or personal path: " + str(relative))
        result.append(path)
    missing = RELEASE_FILES - {path.relative_to(ROOT).as_posix() for path in result}
    if missing:
        raise ValueError("Missing release files: " + ", ".join(sorted(missing)))
    return result


if __name__ == "__main__":
    print("Public source check passed:", len(public_files()), "files; no binaries, credentials or personal home paths found.")
