from __future__ import annotations

import shutil
import subprocess
from typing import Iterable

from .models import MountProfile, ProfileType
from .unit import smb_requires_credentials

APPLICATION_ATTR = "easymount"
LEGACY_APPLICATION_ATTR = "easysmb"


class SecretStoreError(RuntimeError):
    pass


class SecretServiceStore:
    """Secret Service adapter using libsecret's secret-tool CLI."""

    def __init__(self, binary: str = "secret-tool") -> None:
        self.binary = binary

    def available(self) -> bool:
        return shutil.which(self.binary) is not None

    def store(self, profile_id: str, password: str, *, label: str) -> None:
        self._require()
        result = subprocess.run(
            [
                self.binary,
                "store",
                "--label",
                label,
                "application",
                APPLICATION_ATTR,
                "profile",
                profile_id,
            ],
            input=password,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise SecretStoreError(result.stderr.strip() or "secret-tool store failed")

    def lookup(self, profile_id: str) -> str | None:
        self._require()
        return self._lookup(profile_id, APPLICATION_ATTR)

    def migrate_legacy(self, profile_id: str, *, label: str) -> bool:
        """Move a pre-rename ``easysmb`` secret to the ``easymount`` attribute once."""
        self._require()
        if self._lookup(profile_id, APPLICATION_ATTR) is not None:
            return False
        legacy = self._lookup(profile_id, LEGACY_APPLICATION_ATTR)
        if legacy is None:
            return False
        self.store(profile_id, legacy, label=label)
        self._clear(profile_id, LEGACY_APPLICATION_ATTR)
        return True

    def _lookup(self, profile_id: str, application: str) -> str | None:
        result = subprocess.run(
            [
                self.binary,
                "lookup",
                "application",
                application,
                "profile",
                profile_id,
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout.rstrip("\n")
        if result.returncode == 1:
            return None
        raise SecretStoreError(result.stderr.strip() or "secret-tool lookup failed")

    def clear(self, profile_id: str) -> None:
        self._require()
        self._clear(profile_id, APPLICATION_ATTR)

    def _clear(self, profile_id: str, application: str) -> None:
        result = subprocess.run(
            [
                self.binary,
                "clear",
                "application",
                application,
                "profile",
                profile_id,
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode not in {0, 1}:
            raise SecretStoreError(result.stderr.strip() or "secret-tool clear failed")

    def _require(self) -> None:
        if not self.available():
            raise SecretStoreError("secret-tool is not installed")


def migrate_legacy_secrets(profiles: Iterable[MountProfile], store: SecretServiceStore | None = None) -> None:
    """Best-effort one-time migration of saved SMB passwords for known profiles."""
    store = store or SecretServiceStore()
    if not store.available():
        return
    for profile in profiles:
        if profile.type is ProfileType.SMB and profile.password_saved and smb_requires_credentials(profile):
            try:
                store.migrate_legacy(profile.id, label=profile.display_name)
            except SecretStoreError:
                continue
