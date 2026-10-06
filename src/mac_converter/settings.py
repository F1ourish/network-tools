"""Persist appearance only. Entered network addresses are never stored."""

import json
import os
from pathlib import Path
import tempfile


def default_settings_path() -> Path:
    if os.name == "nt":
        parent = Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming")))
    else:
        parent = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
    return parent / "MacAddressConverter" / "settings.json"


class ThemeSettings:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path if path is not None else default_settings_path()

    def load(self) -> str:
        try:
            if self.path.stat().st_size > 8192:
                return "day"
            data = json.loads(self.path.read_text(encoding="utf-8"))
            theme = data.get("theme") if isinstance(data, dict) else None
            return theme if theme in ("day", "night") else "day"
        except (OSError, ValueError, UnicodeError):
            return "day"

    def save(self, theme: str) -> None:
        if theme not in ("day", "night"):
            raise ValueError("Unknown theme")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.path.parent, prefix=".theme-", delete=False
            ) as handle:
                temporary = Path(handle.name)
                json.dump({"theme": theme}, handle)
                handle.write("\n")
            os.replace(temporary, self.path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
