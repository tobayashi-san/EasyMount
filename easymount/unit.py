from __future__ import annotations

from dataclasses import dataclass

from .models import MountProfile, NFSVersion, ProfileType, ValidationError


DEFAULT_SMB_OPTIONS = {
    "iocharset": "utf8",
    "vers": "3.1.1",
    "serverino": "",
    "nosuid": "",
    "nodev": "",
    "nofail": "",
    "_netdev": "",
}

DEFAULT_NFS_OPTIONS = {
    "rw": "",
    "nosuid": "",
    "nodev": "",
    "nofail": "",
    "_netdev": "",
    "hard": "",
    "timeo": "600",
    "retrans": "2",
}


@dataclass(frozen=True, slots=True)
class UnitBundle:
    mount_unit_name: str
    automount_unit_name: str
    mount_unit: str
    automount_unit: str
    mount_path: str
    credential_path: str | None = None


def systemd_escape_path(path: str) -> str:
    stripped = path.strip("/")
    if not stripped:
        return "-"

    result: list[str] = []
    for byte in stripped.encode("utf-8"):
        char = chr(byte)
        if char == "/":
            result.append("-")
        elif char == "-":
            result.append(r"\x2d")
        elif char.isalnum() or char in ":_.":
            result.append(char)
        else:
            result.append(rf"\x{byte:02x}")
    return "".join(result)


def unit_name_for_path(path: str, suffix: str) -> str:
    return f"{systemd_escape_path(path)}.{suffix}"


def smb_source(profile: MountProfile) -> str:
    return f"//{profile.server}/{profile.remote_path}"


def nfs_source(profile: MountProfile) -> str:
    return f"{profile.server}:{profile.remote_path}"


def build_unit_bundle(profile: MountProfile, *, credential_path: str | None = None) -> UnitBundle:
    mount_name = unit_name_for_path(profile.mount_path, "mount")
    automount_name = unit_name_for_path(profile.mount_path, "automount")

    if profile.type is ProfileType.SMB:
        if smb_requires_credentials(profile) and credential_path is None:
            raise ValidationError("SMB unit generation requires a credential path for authenticated shares")
        what = smb_source(profile)
        fs_type = "cifs"
        options = build_smb_options(profile, credential_path)
    elif profile.type is ProfileType.NFS:
        what = nfs_source(profile)
        fs_type = "nfs"
        options = build_nfs_options(profile)
    else:
        raise ValidationError("unsupported profile type")

    mount_unit = "\n".join(
        [
            "[Unit]",
            f"Description=EasyMount mount for {profile.display_name}",
            "Documentation=https://github.com/tobayashi-san/EasyMount",
            "Wants=network-online.target",
            "After=network-online.target",
            "",
            "[Mount]",
            f"What={what}",
            f"Where={profile.mount_path}",
            f"Type={fs_type}",
            f"Options={render_options(options)}",
            "TimeoutSec=30",
            "",
            "[Install]",
            "WantedBy=multi-user.target",
            "",
        ]
    )
    automount_unit = "\n".join(
        [
            "[Unit]",
            f"Description=EasyMount automount for {profile.display_name}",
            "Documentation=https://github.com/tobayashi-san/EasyMount",
            "Wants=network-online.target",
            "After=network-online.target",
            "",
            "[Automount]",
            f"Where={profile.mount_path}",
            "TimeoutIdleSec=300",
            "",
            "[Install]",
            "WantedBy=multi-user.target",
            "",
        ]
    )
    return UnitBundle(
        mount_unit_name=mount_name,
        automount_unit_name=automount_name,
        mount_unit=mount_unit,
        automount_unit=automount_unit,
        mount_path=profile.mount_path,
        credential_path=credential_path,
    )


def build_smb_options(profile: MountProfile, credential_path: str | None = None) -> dict[str, str]:
    options = dict(DEFAULT_SMB_OPTIONS)
    options.update(
        {
            "uid": str(profile.created_for_uid),
            "gid": str(profile.created_for_gid),
            "file_mode": profile.options.get("file_mode", "0600"),
            "dir_mode": profile.options.get("dir_mode", "0700"),
        }
    )
    if credential_path:
        options["credentials"] = credential_path
    else:
        options["guest"] = ""
    for key, value in profile.options.items():
        if key not in {"file_mode", "dir_mode"}:
            options[key] = value
    return options


def smb_requires_credentials(profile: MountProfile) -> bool:
    return bool(profile.username or profile.domain or profile.password_saved)


def build_nfs_options(profile: MountProfile) -> dict[str, str]:
    options = dict(DEFAULT_NFS_OPTIONS)
    version = profile.nfs_version or NFSVersion.V4
    options["vers"] = version.value
    if version is NFSVersion.V3:
        options["proto"] = "tcp"
    options.update(profile.options)
    return options


def render_options(options: dict[str, str]) -> str:
    rendered: list[str] = []
    for key, value in options.items():
        if value == "":
            rendered.append(key)
        else:
            rendered.append(f"{key}={value}")
    return ",".join(rendered)
