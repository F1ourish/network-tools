import json
import os

import pytest

from mac_converter.settings import ThemeSettings, default_settings_path


def test_only_theme_is_persisted_and_replaced_atomically(tmp_path):
    path = tmp_path / "config" / "settings.json"
    settings = ThemeSettings(path)
    assert settings.load() == "day"
    settings.save("night")
    assert ThemeSettings(path).load() == "night"
    assert json.loads(path.read_text()) == {"theme": "night"}
    settings.save("day")
    assert settings.load() == "day"
    assert list(path.parent.iterdir()) == [path]


@pytest.mark.parametrize(
    "content",
    [b"invalid", b"[]", b'{"theme":"unknown"}', b'{"theme":42}', b"{}", b"\xff", b"x" * 8193],
)
def test_bad_settings_fall_back_to_day(tmp_path, content):
    path = tmp_path / "settings.json"
    path.write_bytes(content)
    assert ThemeSettings(path).load() == "day"


def test_failed_replace_preserves_previous_settings_and_cleans_temp(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    settings = ThemeSettings(path)
    settings.save("day")

    def denied(*_args):
        raise PermissionError("read only")

    monkeypatch.setattr(os, "replace", denied)
    with pytest.raises(PermissionError):
        settings.save("night")
    assert settings.load() == "day"
    assert list(tmp_path.iterdir()) == [path]


def test_invalid_theme_is_not_saved(tmp_path):
    path = tmp_path / "settings.json"
    with pytest.raises(ValueError):
        ThemeSettings(path).save("invalid")
    assert not path.exists()


def test_platform_settings_directory(monkeypatch, tmp_path):
    variable = "APPDATA" if os.name == "nt" else "XDG_CONFIG_HOME"
    monkeypatch.setenv(variable, str(tmp_path))
    assert default_settings_path() == tmp_path / "MacAddressConverter" / "settings.json"
