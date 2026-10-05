"""Build using native Windows Python; never label a Linux binary as an EXE."""

import hashlib
import os
from pathlib import Path
import struct
import subprocess
import sys


def main() -> int:
    if os.name != "nt" or struct.calcsize("P") != 8 or sys.version_info[:3] != (3, 12, 10):
        raise SystemExit("Use Windows CPython 3.12.10 x64 for this release build.")
    root = Path(__file__).resolve().parents[1]
    subprocess.run([sys.executable, "-m", "pytest", "-q", "--require-gui"], cwd=root, check=True)
    subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm", "mac-converter.spec"],
        cwd=root,
        check=True,
    )
    binary = root / "dist" / "MacAddressConverter.exe"
    if not binary.is_file():
        raise SystemExit("Build did not produce dist/MacAddressConverter.exe")
    checksum = hashlib.sha256(binary.read_bytes()).hexdigest()
    (binary.parent / "SHA256SUMS.txt").write_text(f"{checksum}  {binary.name}\n", encoding="ascii")
    subprocess.run(
        [sys.executable, str(root / "scripts" / "smoke_windows.py"), str(binary)],
        cwd=root,
        check=True,
    )
    print(f"Verified artifact: {binary} ({binary.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
