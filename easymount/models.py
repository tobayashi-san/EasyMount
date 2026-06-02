from __future__ import annotations

import os
import re
import unicodedata
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class ValidationError(ValueError):
    """Raised when a mount profile is unsafe or incomplete."""


class ProfileType(str, Enum):
    SMB = "smb"
    NFS = "nfs"


class NFSVersion(str, Enum):
    V3 = "3"
    V4 = "4"


class MountMode(str, Enum):
    AUTOMOUNT = "automount"
    ALWAYS = "always"


_PROFILE_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
_OPTION_RE = re.compile(r"^[A-Za-z0-9_.:-]+$")


@dataclass(slots=True)
class MountProfile:
    id: str
    type: ProfileType
    display_name: str
    server: str
    remote_path: str
    mount_path: str
    enabled: bool = True
    mount_mode: MountMode = MountMode.AUTOMOUNT
    options: dict[str, str] = field(default_factory=dict)
    created_for_uid: int = field(default_factory=os.getuid)
    created_for_gid: int = field(default_factory=os.getgid)
    username: str | None = None
    domain: str | None = None
    password_saved: bool = False
    nfs_version: NFSVersion | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MountProfile":
        profile_type = ProfileType(data["type"])
        nfs_version = data.get("nfs_version")
        return cls(
            id=str(data["id"]),
            type=profile_type,
            display_name=str(data["display_name"]),
            server=str(data["server"]),
            remote_path=str(data["remote_path"]),
            mount_path=str(data["mount_path"]),
            enabled=bool(data.get("enabled", True)),
            mount_mode=MountMode(str(data.get("mount_mode", MountMode.AUTOMOUNT.value))),
            options={str(k): str(v) for k, v in data.get("options", {}).items()},
            created_for_uid=int(data.get("created_for_uid", os.getuid())),
            created_for_gid=int(data.get("created_for_gid", os.getgid())),
            username=data.get("username"),
            domain=data.get("domain"),
            password_saved=bool(data.get("password_saved", False)),
            nfs_version=NFSVersion(str(nfs_version)) if nfs_version else None,
        )

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.id,
            "type": self.type.value,
            "display_name": self.display_name,
            "server": self.server,
            "remote_path": self.remote_path,
            "mount_path": self.mount_path,
            "enabled": self.enabled,
            "mount_mode": self.mount_mode.value,
            "options": dict(self.options),
            "created_for_uid": self.created_for_uid,
            "created_for_gid": self.created_for_gid,
        }
        if self.username:
            data["username"] = self.username
        if self.domain:
            data["domain"] = self.domain
        if self.password_saved:
            data["password_saved"] = self.password_saved
        if self.nfs_version:
            data["nfs_version"] = self.nfs_version.value
        return data


def slugify_mount_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore")
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", normalized.decode()).strip(".-")
    return slug[:48] or "share"


def new_profile_id(display_name: str) -> str:
    return f"{slugify_mount_name(display_name).lower()}-{uuid.uuid4().hex[:8]}"


def default_mount_path(display_name: str, home: str | os.PathLike[str] | None = None) -> str:
    base = Path(home) if home is not None else Path.home()
    return str(base / "Network" / slugify_mount_name(display_name))


def validate_profile(
    profile: MountProfile,
    *,
    user_home: str | os.PathLike[str] | None = None,
) -> None:
    errors: list[str] = []

    if not _PROFILE_ID_RE.match(profile.id):
        errors.append("profile id must contain only letters, numbers, dot, dash or underscore")
    if not profile.display_name.strip():
        errors.append("display name is required")
    elif _has_control_characters(profile.display_name):
        errors.append("display name must not contain control characters or line breaks")
    if not profile.server.strip() or any(ch.isspace() for ch in profile.server) or "/" in profile.server:
        errors.append("server must be a hostname or address without whitespace or slashes")
    if "\x00" in profile.mount_path or "\n" in profile.mount_path:
        errors.append("mount path contains invalid characters")

    mount_path = Path(profile.mount_path)
    if not mount_path.is_absolute():
        errors.append("mount path must be absolute")
    if ".." in mount_path.parts:
        errors.append("mount path must not contain parent traversal")
    if str(mount_path) in {"/", "/home", "/mnt", "/media"}:
        errors.append("mount path is too broad")
    if user_home is not None:
        network_root = Path(user_home) / "Network"
        try:
            common = os.path.commonpath([str(mount_path), str(network_root)])
            if common != str(network_root):
                errors.append(f"mount path must be below {network_root}")
        except ValueError:
            errors.append("mount path and user home are on incompatible paths")

    if profile.mount_mode not in {MountMode.AUTOMOUNT, MountMode.ALWAYS}:
        errors.append("mount mode must be automount or always")

    if profile.type is ProfileType.SMB:
        if not profile.remote_path.strip():
            errors.append("SMB share name is required")
        if profile.remote_path.startswith("/") or "/" in profile.remote_path:
            errors.append(
                "SMB share must be only the exported share name; "
                "do not enter a server filesystem path like /volume1/test"
            )
        if any(ch.isspace() for ch in profile.remote_path):
            errors.append("SMB share names with whitespace are not supported in v1")
        if profile.username is not None and _has_credential_newline(profile.username):
            errors.append("SMB username contains invalid characters")
        if profile.domain is not None and _has_credential_newline(profile.domain):
            errors.append("SMB domain contains invalid characters")
    elif profile.type is ProfileType.NFS:
        if not profile.remote_path.startswith("/"):
            errors.append("NFS export path must start with /")
        if ".." in Path(profile.remote_path).parts:
            errors.append("NFS export path must not contain parent traversal")
        if profile.nfs_version not in {NFSVersion.V3, NFSVersion.V4}:
            errors.append("NFS version must be 3 or 4")
    else:
        errors.append("unsupported profile type")

    for key, value in profile.options.items():
        if not _OPTION_RE.match(key):
            errors.append(f"invalid option key: {key}")
        if any(ch in value for ch in [",", "\n", "\x00"]):
            errors.append(f"invalid option value for {key}")

    if errors:
        raise ValidationError("; ".join(errors))


def _has_credential_newline(value: str) -> bool:
    return "\n" in value or "\r" in value or "\x00" in value


def _has_control_characters(value: str) -> bool:
    return any(unicodedata.category(ch) in {"Cc", "Cf", "Zl", "Zp"} for ch in value)
