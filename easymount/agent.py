from __future__ import annotations

import json
import subprocess
import sys

from .launcher import HelperLaunchError, helper_command
from .models import MountMode, ProfileType
from .secret_store import SecretServiceStore, SecretStoreError
from .storage import ProfileStore
from .unit import smb_requires_credentials


def main() -> int:
    store = ProfileStore()
    secret_store = SecretServiceStore()
    profiles = store.load()
    failures: list[str] = []

    for profile in profiles:
        if not profile.enabled:
            continue

        payload = {"profile": profile.to_dict()}
        if profile.type is ProfileType.SMB and smb_requires_credentials(profile):
            try:
                secret = secret_store.lookup(profile.id) if profile.password_saved else ""
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
