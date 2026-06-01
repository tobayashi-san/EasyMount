from __future__ import annotations

import os
import shutil
from pathlib import Path

from .constants import HELPER_COMMAND, HELPER_ENV, HOST_HELPER_CANDIDATES, HOST_HELPER_PATH, LEGACY_HELPER_ENV


class HelperLaunchError(RuntimeError):
    pass


def helper_executable() -> str:
    configured = os.environ.get(HELPER_ENV) or os.environ.get(LEGACY_HELPER_ENV)
    if configured:
        return configured
    if is_flatpak():
        return HOST_HELPER_PATH
    for candidate in HOST_HELPER_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    return shutil.which(HELPER_COMMAND) or HELPER_COMMAND


def is_flatpak() -> bool:
    return Path("/.flatpak-info").exists()


def helper_command(command: str, *, privileged: bool = False) -> list[str]:
    executable = helper_executable()
    if is_flatpak():
        flatpak_spawn = shutil.which("flatpak-spawn") or "/usr/bin/flatpak-spawn"
        if not privileged:
            return [flatpak_spawn, "--host", "/bin/sh", "-lc", host_helper_resolver_script(), HELPER_COMMAND, command]
        if privileged and os.geteuid() != 0:
            return [flatpak_spawn, "--host", "pkexec", executable, command]
        return [flatpak_spawn, "--host", executable, command]

    if privileged and os.geteuid() != 0:
        pkexec = shutil.which("pkexec")
        if not pkexec:
            raise HelperLaunchError("pkexec is not installed")
        return [pkexec, executable, command]

    return [executable, command]


def host_helper_resolver_script() -> str:
    candidates = " ".join(f"'{candidate}'" for candidate in HOST_HELPER_CANDIDATES)
    return (
        f"for helper in {candidates}; do "
        'if [ -x "$helper" ]; then exec "$helper" "$@"; fi; '
        "done; "
        f'exec {HELPER_COMMAND} "$@"'
    )
