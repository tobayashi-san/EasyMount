from __future__ import annotations

import json
import subprocess
import sys
import time

from .launcher import HelperLaunchError, helper_command
from .models import MountMode, MountProfile, ProfileType
from .secret_store import SecretServiceStore, SecretStoreError, migrate_legacy_secrets
from .storage import ProfileStore
from .unit import smb_requires_credentials


SECRET_LOOKUP_ATTEMPTS = 15
SECRET_LOOKUP_DELAY_SECONDS = 1.0


def main() -> int:
    store = ProfileStore()
    secret_store = SecretServiceStore()
    profiles = store.load()
    migrate_legacy_secrets(profiles, secret_store)
    failures: list[str] = []

    for profile in profiles:
        if not profile.enabled:
            continue

        payload = {"profile": profile.to_dict()}
        if profile.type is ProfileType.SMB and smb_requires_credentials(profile):
            try:
                secret = lookup_saved_secret(secret_store, profile) if profile.password_saved else ""
            except SecretStoreError as exc:
                failures.append(f"{profile.display_name}: {exc}")
                continue
            if profile.password_saved and not secret:
                failures.append(f"{profile.display_name}: missing secret")
                continue
            payload["secret"] = secret
            result = run_helper("prepare-credentials", payload)
            if result.returncode != 0:
                failures.append(f"{profile.display_name}: {result.stderr.strip() or result.stdout.strip()}")
                continue

        if profile.mount_mode == MountMode.ALWAYS:
            result = run_helper("mount-now", payload)
            if result.returncode != 0:
                failures.append(f"{profile.display_name}: {result.stderr.strip() or result.stdout.strip()}")

    for failure in failures:
        print(failure, file=sys.stderr)
    return 1 if failures else 0


def lookup_saved_secret(secret_store: SecretServiceStore, profile: MountProfile) -> str | None:
    last_error: SecretStoreError | None = None
    for attempt in range(SECRET_LOOKUP_ATTEMPTS):
        try:
            secret = secret_store.lookup(profile.id)
        except SecretStoreError as exc:
            last_error = exc
            secret = None

        if secret:
            return secret

        if attempt < SECRET_LOOKUP_ATTEMPTS - 1:
            time.sleep(SECRET_LOOKUP_DELAY_SECONDS)

    if last_error is not None:
        raise last_error
    return None


def run_helper(command: str, payload: dict) -> subprocess.CompletedProcess[str]:
    try:
        cmd = helper_command(command, privileged=True)
    except HelperLaunchError as exc:
        return subprocess.CompletedProcess([command], 1, stdout="", stderr=str(exc))
    return subprocess.run(
        cmd,
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=False,
    )


if __name__ == "__main__":
    raise SystemExit(main())
