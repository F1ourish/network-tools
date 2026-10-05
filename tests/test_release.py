from pathlib import Path
from runpy import run_path

import pytest

check_tag = run_path(str(Path(__file__).resolve().parents[1] / "scripts" / "check_release_tag.py"))[
    "check_tag"
]


def test_matching_release_tag():
    check_tag("v1.0.0", "1.0.0")


@pytest.mark.parametrize("tag", ["1.0.0", "v1.0.1", "v1.0.0-rc1", "v1.0.0\n"])
def test_invalid_release_tag(tag):
    with pytest.raises(ValueError):
        check_tag(tag, "1.0.0")
