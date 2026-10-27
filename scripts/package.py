#!/usr/bin/env python3
"""Create a source-only ZIP from the checked release allowlist."""
import hashlib
from pathlib import Path
import zipfile

from check_public import ROOT, public_files

files = public_files()
destination = ROOT / "dist"
destination.mkdir(exist_ok=True)
archive = destination / "android-local-agent-v0.1.0.zip"
checksums = []
with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as output:
    for path in files:
        relative = path.relative_to(ROOT).as_posix()
        data = path.read_bytes()
        entry = zipfile.ZipInfo("android-local-agent/" + relative)
        entry.create_system = 3
        executable = path.suffix == ".sh" or relative == "src/phone_agent.py"
        entry.external_attr = (0o100755 if executable else 0o100644) << 16
        entry.compress_type = zipfile.ZIP_DEFLATED
        output.writestr(entry, data)
        checksums.append(hashlib.sha256(data).hexdigest() + "  " + relative)
    output.writestr("android-local-agent/SOURCE-SHA256SUMS", "\n".join(checksums) + "\n")
with zipfile.ZipFile(archive) as verify:
    assert len(verify.namelist()) == len(files) + 1
    assert verify.testzip() is None
    for path in files:
        relative = path.relative_to(ROOT).as_posix()
        assert verify.read("android-local-agent/" + relative) == path.read_bytes()
digest = hashlib.sha256(archive.read_bytes()).hexdigest()
(destination / "SHA256SUMS").write_text(digest + "  " + archive.name + "\n", encoding="utf-8")
print(archive.name, archive.stat().st_size, "bytes;", len(files), "source files; verified")
print("SHA256", digest)
