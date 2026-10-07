import hashlib
import json
from pathlib import Path
from runpy import run_path

import pytest

checked_assets = run_path(str(Path(__file__).resolve().parents[1] / "scripts/publish_release.py"))[
    "checked_assets"
]


@pytest.fixture
def release_assets(tmp_path):
    binary = tmp_path / "NetworkTools.exe"
    binary.write_bytes(b"tested windows exe")
    (tmp_path / "NetworkTools-1.3.1-windows-x64.zip").write_bytes(b"portable zip")
    (tmp_path / "RELEASE_VERIFICATION.json").write_text(
        json.dumps(
            {
                "version": "1.3.1",
                "commit": "checked-commit",
                "smoke": {
                    "passed": True,
                    "sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
                },
            }
        )
    )
    files = sorted(tmp_path.iterdir())
    (tmp_path / "SHA256SUMS.txt").write_text(
        "".join(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n" for path in files)
    )
    return tmp_path


def test_publisher_accepts_complete_checked_assets(release_assets):
    assets = checked_assets(release_assets, "1.3.1", "checked-commit")
    assert {path.name for path in assets} == {
        "NetworkTools.exe",
        "NetworkTools-1.3.1-windows-x64.zip",
        "RELEASE_VERIFICATION.json",
        "SHA256SUMS.txt",
    }


@pytest.mark.parametrize("version,commit", [("1.3.0", "checked-commit"), ("1.3.1", "other-commit")])
def test_publisher_rejects_different_source(release_assets, version, commit):
    with pytest.raises(ValueError, match="version or commit"):
        checked_assets(release_assets, version, commit)


def test_publisher_rejects_modified_binary(release_assets):
    (release_assets / "NetworkTools.exe").write_bytes(b"changed after test")
    with pytest.raises(ValueError, match="Checksum mismatch"):
        checked_assets(release_assets, "1.3.1", "checked-commit")


def test_publisher_rejects_unverified_exe(release_assets):
    path = release_assets / "RELEASE_VERIFICATION.json"
    report = json.loads(path.read_text())
    report["smoke"]["passed"] = False
    path.write_text(json.dumps(report))
    with pytest.raises(ValueError, match="did not pass"):
        checked_assets(release_assets, "1.3.1", "checked-commit")


def test_publisher_rejects_missing_or_unexpected_assets(release_assets):
    sums = release_assets / "SHA256SUMS.txt"
    original = sums.read_text()
    sums.write_text(original.splitlines()[0] + "\n")
    with pytest.raises(ValueError, match="Missing"):
        checked_assets(release_assets, "1.3.1", "checked-commit")
    sums.write_text(original + "0  ../unexpected.exe\n")
    with pytest.raises(ValueError, match="Unexpected"):
        checked_assets(release_assets, "1.3.1", "checked-commit")
