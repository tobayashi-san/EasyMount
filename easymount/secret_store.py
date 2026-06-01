from __future__ import annotations

import shutil
import subprocess

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
        result = self._lookup(profile_id, APPLICATION_ATTR)
        if result is not None:
            return result
        return self._lookup(profile_id, LEGACY_APPLICATION_ATTR)

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
        for application in [APPLICATION_ATTR, LEGACY_APPLICATION_ATTR]:
            self._clear(profile_id, application)

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
