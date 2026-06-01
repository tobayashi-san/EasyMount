from __future__ import annotations

from pathlib import Path


APP_ID = "org.easymount.EasyMount"
APP_NAME = "EasyMount"
VERSION = "0.1.0"
ICON_NAME = APP_ID
SOURCE_ICON_DIR = Path(__file__).resolve().parent.parent / "data" / "icons"

HELPER_ENV = "EASYMOUNT_HELPER"
LEGACY_HELPER_ENV = "EASYSMB_HELPER"
HOST_HELPER_PATH = "/usr/libexec/easymount-helper"
HELPER_COMMAND = "easymount-helper"
HOST_HELPER_CANDIDATES = [
    "/usr/libexec/easymount-helper",
    "/usr/local/libexec/easymount-helper",
    "/usr/bin/easymount-helper",
    "/usr/local/bin/easymount-helper",
]
