"""Build using native Windows Python; never label a Linux binary as an EXE."""

import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import platform
import struct
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile


def main() -> int:
    if os.name != "nt" or struct.calcsize("P") != 8 or sys.version_info[:3] != (3, 12, 10):
        raise SystemExit("Use Windows CPython 3.12.10 x64 for this release build.")
    root = Path(__file__).resolve().parents[1]
    results = root / "smoke-results"
    results.mkdir(exist_ok=True)
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "--require-gui",
            "--junitxml=smoke-results/pytest.xml",
        ],
        cwd=root,
        check=True,
    )
    subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm", "mac-converter.spec"],
        cwd=root,
        check=True,
    )
    binary = root / "dist" / "NetworkTools.exe"
    if not binary.is_file():
        raise SystemExit("Build did not produce dist/NetworkTools.exe")
    subprocess.run(
        [sys.executable, str(root / "scripts" / "smoke_windows.py"), str(binary)],
        cwd=root,
        check=True,
    )
    from mac_converter import __version__
    from PyInstaller.archive.readers import CArchiveReader

    report = json.loads((results / "windows-exe.json").read_text(encoding="utf-8"))
    assert report["passed"] is True
    suites = ET.parse(results / "pytest.xml").getroot().findall("testsuite")
    test_counts = {
        key: sum(int(suite.attrib.get(key, 0)) for suite in suites)
        for key in ("tests", "failures", "errors", "skipped")
    }
    assert test_counts["tests"] > 0 and not any(
        test_counts[key] for key in ("failures", "errors", "skipped")
    )
    metadata = {
        "version": __version__,
        "commit": os.environ.get("GITHUB_SHA"),
        "run_id": os.environ.get("GITHUB_RUN_ID"),
        "platform": platform.platform(),
        "runner_image": os.environ.get("ImageVersion"),
        "python": sys.version,
        "dependencies": {name: version(name) for name in ("ttkbootstrap", "Pillow", "pyinstaller")},
        "pytest": test_counts,
        "smoke": report,
    }
    verification = binary.parent / "RELEASE_VERIFICATION.json"
    verification.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    portable = binary.parent / f"NetworkTools-{__version__}-windows-x64.zip"
    archive = CArchiveReader(str(binary))
    with zipfile.ZipFile(portable, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.write(binary, binary.name)
        bundle.write(root / "LICENSE", "LICENSE.txt")
        bundle.write(root / "THIRD_PARTY_NOTICES.md", "THIRD_PARTY_NOTICES.md")
        bundle.write(root / "docs" / "PORTABLE_README.txt", "README.txt")
        bundle.write(verification, verification.name)
        for name in sorted(archive.toc):
            normalized = name.replace("\\", "/")
            if normalized.startswith("third_party/"):
                bundle.writestr(normalized, archive.extract(name))
    assets = (binary, portable, verification)
    (binary.parent / "SHA256SUMS.txt").write_text(
        "".join(
            f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n" for path in assets
        ),
        encoding="ascii",
    )
    print(f"Verified artifact: {binary} ({binary.stat().st_size} bytes)")
    print(f"Portable bundle: {portable.name} ({portable.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
