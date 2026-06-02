from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .storage import default_config_dir, legacy_config_dir


VALID_THEMES = {"system", "light", "dark"}


def normalize_theme(value: object) -> str:
    if isinstance(value, str) and value in VALID_THEMES:
        return value
    return "system"


@dataclass(slots=True)
class AppSettings:
    show_in_file_browser: bool = False
    theme: str = "system"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AppSettings":
        return cls(
            show_in_file_browser=bool(data.get("show_in_file_browser", False)),
            theme=normalize_theme(data.get("theme")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "show_in_file_browser": self.show_in_file_browser,
            "theme": normalize_theme(self.theme),
        }


class SettingsStore:
    def __init__(self, config_dir: str | os.PathLike[str] | None = None) -> None:
        self.config_dir = Path(config_dir) if config_dir is not None else default_config_dir()
        self.path = self.config_dir / "settings.json"
        self._legacy_path = None if config_dir is not None else legacy_config_dir() / "settings.json"

    def load(self) -> AppSettings:
        if not self.path.exists():
            self._migrate_legacy()
        if not self.path.exists():
            return AppSettings()
        with self.path.open("r", encoding="utf-8") as handle:
            return AppSettings.from_dict(json.load(handle))

    def _migrate_legacy(self) -> None:
        """One-time copy of pre-rename ``easysmb`` settings into the new location."""
        if self._legacy_path is None or not self._legacy_path.exists():
            return
        with self._legacy_path.open("r", encoding="utf-8") as handle:
            self.save(AppSettings.from_dict(json.load(handle)))

    def save(self, settings: AppSettings) -> None:
        self.config_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            prefix="settings.",
            suffix=".json",
            dir=self.config_dir,
            text=True,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(settings.to_dict(), handle, indent=2, sort_keys=True)
                handle.write("\n")
            os.chmod(tmp_name, 0o600)
            os.replace(tmp_name, self.path)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)
