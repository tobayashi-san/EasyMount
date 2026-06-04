from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .models import MountProfile


def config_root() -> Path:
    override = os.environ.get("EASYMOUNT_CONFIG_HOME")
    if override:
        return Path(override)
    xdg_config = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config:
        return Path(xdg_config)
    return Path.home() / ".config"


def default_config_dir() -> Path:
    return config_root() / "easymount"


def legacy_config_dir() -> Path:
    return config_root() / "easysmb"


class ProfileStore:
    def __init__(self, config_dir: str | os.PathLike[str] | None = None) -> None:
        self.config_dir = Path(config_dir) if config_dir is not None else default_config_dir()
        self.path = self.config_dir / "profiles.json"
        self._legacy_path = None if config_dir is not None else legacy_config_dir() / "profiles.json"

    def load(self) -> list[MountProfile]:
        if not self.path.exists():
            self._migrate_legacy()
        if not self.path.exists():
            return []
        with self.path.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)
        return [MountProfile.from_dict(item) for item in raw.get("profiles", [])]

    def _migrate_legacy(self) -> None:
        """One-time copy of pre-rename ``easysmb`` profiles into the new location."""
        if self._legacy_path is None or not self._legacy_path.exists():
            return
        self.config_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        with self._legacy_path.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)
        profiles = [MountProfile.from_dict(item) for item in raw.get("profiles", [])]
        self.save_all(profiles)

    def save_all(self, profiles: list[MountProfile]) -> None:
        self.config_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        payload = {"profiles": [profile.to_dict() for profile in profiles]}
        fd, tmp_name = tempfile.mkstemp(
            prefix="profiles.",
            suffix=".json",
            dir=self.config_dir,
            text=True,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
                handle.write("\n")
            os.chmod(tmp_name, 0o600)
            os.replace(tmp_name, self.path)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)

    def upsert(self, profile: MountProfile) -> None:
        profiles = [item for item in self.load() if item.id != profile.id]
        profiles.append(profile)
        profiles.sort(key=lambda item: item.display_name.lower())
        self.save_all(profiles)

    def delete(self, profile_id: str) -> MountProfile | None:
        profiles = self.load()
        removed = next((item for item in profiles if item.id == profile_id), None)
        self.save_all([item for item in profiles if item.id != profile_id])
        return removed
