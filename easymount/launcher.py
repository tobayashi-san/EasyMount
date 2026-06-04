from __future__ import annotations

import os
import shutil
from pathlib import Path

from .constants import HELPER_COMMAND, HELPER_ENV, HOST_HELPER_CANDIDATES


class HelperLaunchError(RuntimeError):
    pass


def helper_executable() -> str:
    configured = os.environ.get(HELPER_ENV)
    if configured:
        return configured
    for candidate in HOST_HELPER_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    return shutil.which(HELPER_COMMAND) or HELPER_COMMAND


def helper_command(command: str, *, privileged: bool = False) -> list[str]:
    executable = helper_executable()
    if privileged and os.geteuid() != 0:
        pkexec = shutil.which("pkexec")
        if not pkexec:
            raise HelperLaunchError("pkexec is not installed")
        return [pkexec, executable, command]

    return [executable, command]
