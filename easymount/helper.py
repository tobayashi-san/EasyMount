from __future__ import annotations

import argparse
import json
import os
import pwd
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from .constants import VERSION
from .models import MountMode, MountProfile, ProfileType, ValidationError, validate_profile
from .unit import (
    UnitBundle,
    build_nfs_options,
    build_smb_options,
    build_unit_bundle,
    render_options,
    smb_requires_credentials,
    unit_name_for_path,
)


RUNTIME_DIR = Path("/run/easymount")
CREDENTIAL_DIR = RUNTIME_DIR / "credentials"
PROBE_DIR = RUNTIME_DIR / "probe"
DEFAULT_SYSTEMD_DIR = Path("/etc/systemd/system")

CORE_DEPENDENCIES = ["systemctl", "findmnt", "mount", "umount", "pkexec"]
SMB_DEPENDENCIES = ["mount.cifs"]
NFS_DEPENDENCIES = ["mount.nfs"]


class HelperError(RuntimeError):
    def __init__(self, code: str, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.details = details or {}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="easymount-helper")
    subparsers = parser.add_subparsers(dest="command", required=True)

    for name in COMMANDS:
        command = subparsers.add_parser(name)
        command.add_argument("--dry-run", action="store_true")

    args = parser.parse_args(argv)

    try:
        payload = read_payload(sys.stdin)
        result = dispatch(args, payload)
        write_response({"ok": True, **result})
        return 0
    except HelperError as exc:
        write_response({"ok": False, "error": {"code": exc.code, "message": str(exc), **exc.details}})
        return 1
    except (KeyError, ValueError, ValidationError, json.JSONDecodeError) as exc:
        write_response({"ok": False, "error": {"code": "invalid_request", "message": str(exc)}})
        return 1
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode() if isinstance(exc.stderr, bytes) else exc.stderr
        write_response(
            {
                "ok": False,
                "error": {
                    "code": "command_failed",
                    "message": (stderr or str(exc)).strip(),
                    "returncode": exc.returncode,
                },
            }
        )
        return 1


def dispatch(args: argparse.Namespace, payload: dict[str, Any]) -> dict[str, Any]:
    handler = COMMANDS.get(args.command)
    if handler is None:
        raise HelperError("invalid_request", f"unknown command: {args.command}")
    return handler(args, payload)


def read_payload(stream: Any) -> dict[str, Any]:
    raw = stream.read()
    if not raw.strip():
        return {}
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise HelperError("invalid_request", "payload must be a JSON object")
    return data


def write_response(payload: dict[str, Any]) -> None:
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")


def payload_profile(payload: dict[str, Any]) -> MountProfile:
    profile_data = payload.get("profile", payload)
    if not isinstance(profile_data, dict):
        raise HelperError("invalid_request", "profile must be a JSON object")
    profile = MountProfile.from_dict(profile_data)
    validate_profile_for_user(profile)
    return profile


def validate_profile_for_user(profile: MountProfile) -> None:
    user = pwd.getpwuid(profile.created_for_uid)
    validate_profile(profile, user_home=user.pw_dir)
    validate_profile_owner(profile, user)


def validate_profile_owner(profile: MountProfile, user: pwd.struct_passwd) -> None:
    caller_uid = polkit_caller_uid()
    if caller_uid is None:
        return
    if profile.created_for_uid != caller_uid:
        raise HelperError("permission_denied", "profile owner does not match the Polkit caller")
    allowed_gids = set(os.getgrouplist(user.pw_name, user.pw_gid))
    if profile.created_for_gid not in allowed_gids:
        raise HelperError("permission_denied", "profile group does not belong to the Polkit caller")


def polkit_caller_uid() -> int | None:
    raw_uid = os.environ.get("PKEXEC_UID")
    if raw_uid is None:
        return None
    try:
        uid = int(raw_uid)
    except ValueError as exc:
        raise HelperError("permission_denied", "invalid Polkit caller uid") from exc
    if uid < 0:
        raise HelperError("permission_denied", "invalid Polkit caller uid")
    return uid


def handle_validate_profile(args: argparse.Namespace, payload: dict[str, Any]) -> dict[str, Any]:
    profile = payload_profile(payload)
    return {"profile": profile.to_dict()}


def handle_self_check(args: argparse.Namespace, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": VERSION,
        "runtime_dir": str(RUNTIME_DIR),
        "systemd_dir": str(systemd_dir()),
        "requirements": requirements_report(),
    }


def handle_prepare_credentials(args: argparse.Namespace, payload: dict[str, Any]) -> dict[str, Any]:
    profile = payload_profile(payload)
    if profile.type is not ProfileType.SMB:
        raise HelperError("invalid_request", "credentials are only used for SMB profiles")
    if not smb_requires_credentials(profile):
        return {"credential_path": None}
    require_root(args.dry_run)
    credential_path = credential_path_for(profile)
    secret = read_secret(payload, required=profile.password_saved)
    if not args.dry_run:
        write_credentials_file(profile, credential_path, secret)
        disable_boot_mount_for_runtime_credentials(profile)
    return {"credential_path": str(credential_path)}


def handle_install_mount(args: argparse.Namespace, payload: dict[str, Any]) -> dict[str, Any]:
    profile = payload_profile(payload)
    require_root(args.dry_run)
    if not args.dry_run:
        assert_dependencies(profile)

    credential_path = credential_path_for(profile) if profile.type is ProfileType.SMB and smb_requires_credentials(profile) else None
    if profile.type is ProfileType.SMB:
        if smb_requires_credentials(profile):
            secret = read_secret(payload, required=profile.password_saved)
            if not args.dry_run:
                write_credentials_file(profile, credential_path, secret)
        elif not args.dry_run:
            credential_path_for(profile).unlink(missing_ok=True)

    bundle = build_unit_bundle(profile, credential_path=str(credential_path) if credential_path else None)
    if args.dry_run:
        return bundle_response(bundle)

    ensure_mountpoint(profile)
    write_unit_files(bundle)
    systemctl("daemon-reload")
    if profile.enabled:
        activate_profile_units(profile, bundle)
    return {"installed": True, **bundle_response(bundle)}


def handle_remove_mount(args: argparse.Namespace, payload: dict[str, Any]) -> dict[str, Any]:
    profile = payload_profile(payload)
    require_root(args.dry_run)
    bundle = build_unit_bundle_for_existing(profile)

    if args.dry_run:
        return bundle_response(bundle)

    run(["systemctl", "stop", bundle.automount_unit_name], check=False)
    unmount_profile(profile, bundle)
    for unit_name in [bundle.mount_unit_name, bundle.automount_unit_name]:
        run(["systemctl", "disable", unit_name], check=False)
    for unit_name in [bundle.automount_unit_name, bundle.mount_unit_name]:
        unit_path(unit_name).unlink(missing_ok=True)
    credential_path_for(profile).unlink(missing_ok=True)
    systemctl("daemon-reload")
    remove_empty_mountpoint(profile)
    return {"removed": True}


def handle_mount_now(args: argparse.Namespace, payload: dict[str, Any]) -> dict[str, Any]:
    profile = payload_profile(payload)
    require_root(args.dry_run)
    if profile.type is ProfileType.SMB and smb_requires_credentials(profile):
        secret = read_secret(payload, required=profile.password_saved)
        if not args.dry_run:
            write_credentials_file(profile, credential_path_for(profile), secret)
    unit_name = unit_name_for_path(profile.mount_path, "mount")
    if not args.dry_run:
        systemctl("start", unit_name)
    return {"started": unit_name}


def handle_unmount_now(args: argparse.Namespace, payload: dict[str, Any]) -> dict[str, Any]:
    profile = payload_profile(payload)
    require_root(args.dry_run)
    bundle = build_unit_bundle_for_existing(profile)
    if not args.dry_run:
        unmount_profile(profile, bundle)
    return {
        "stopped": bundle.mount_unit_name,
        "automount_unit": bundle.automount_unit_name,
        "mounted": False,
    }


def handle_status(args: argparse.Namespace, payload: dict[str, Any]) -> dict[str, Any]:
    profile = payload_profile(payload)
    mount_info = network_mount_info(profile)
    mount_unit = unit_name_for_path(profile.mount_path, "mount")
    automount_unit = unit_name_for_path(profile.mount_path, "automount")
    return {
        "mounted": mount_info["mounted"],
        "fstype": mount_info["fstype"],
        "source": mount_info["source"],
        "mount_unit": mount_unit,
        "automount_unit": automount_unit,
        "mount_active": systemctl_status("is-active", mount_unit),
        "mount_enabled": systemctl_status("is-enabled", mount_unit),
        "automount_active": systemctl_status("is-active", automount_unit),
        "automount_enabled": systemctl_status("is-enabled", automount_unit),
        "mode": profile.mount_mode.value,
    }


def handle_test_connection(args: argparse.Namespace, payload: dict[str, Any]) -> dict[str, Any]:
    profile = payload_profile(payload)
    if not args.dry_run:
        assert_dependencies(profile)
    require_root(args.dry_run)

    if args.dry_run:
        return {
            "probe": "dry-run",
            "dependencies": dependency_names(profile),
            "missing": [name for name in dependency_names(profile) if find_executable(name) is None],
        }

    PROBE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    probe_path = Path(tempfile.mkdtemp(prefix=f"{profile.id}.", dir=PROBE_DIR))
    credential_path: Path | None = None
    try:
        if profile.type is ProfileType.SMB:
            if smb_requires_credentials(profile):
                credential_path = probe_path / "credentials"
                write_credentials_file(profile, credential_path, read_secret(payload, required=profile.password_saved))
                options = build_smb_options(profile, str(credential_path))
            else:
                options = build_smb_options(profile)
            what = f"//{profile.server}/{profile.remote_path}"
            fs_type = "cifs"
        else:
            options = build_nfs_options(profile)
            what = f"{profile.server}:{profile.remote_path}"
            fs_type = "nfs"
        options["ro"] = ""
        run(["mount", "-t", fs_type, "-o", render_options(options), what, str(probe_path)])
        run(["umount", str(probe_path)], check=False)
        return {"probe": "ok"}
    finally:
        if is_mounted(str(probe_path)):
            run(["umount", str(probe_path)], check=False)
        if credential_path:
            credential_path.unlink(missing_ok=True)
        try:
            probe_path.rmdir()
        except OSError:
            pass


def require_root(dry_run: bool) -> None:
    if not dry_run and os.geteuid() != 0:
        raise HelperError("permission_denied", "this action must run as root through Polkit")


def read_secret(payload: dict[str, Any], *, required: bool) -> str:
    secret = payload.get("secret")
    if secret is None and not required:
        return ""
    if not isinstance(secret, str) or (required and not secret):
        raise HelperError("missing_secret", "SMB password is required")
    if "\n" in secret or "\r" in secret or "\x00" in secret:
        raise HelperError("invalid_secret", "SMB password contains unsupported characters")
    return secret


def assert_dependencies(profile: MountProfile) -> None:
    missing = [name for name in dependency_names(profile) if find_executable(name) is None]
    if missing:
        raise HelperError(
            "missing_dependency",
            f"missing required command: {', '.join(missing)}",
            details={"missing": missing},
        )


def dependency_names(profile: MountProfile) -> list[str]:
    if profile.type is ProfileType.SMB:
        return ["mount.cifs", "systemctl"]
    return ["mount.nfs", "systemctl"]


def requirements_report() -> dict[str, Any]:
    commands = {
        name: find_executable(name)
        for name in [*CORE_DEPENDENCIES, *SMB_DEPENDENCIES, *NFS_DEPENDENCIES]
    }
    systemd = systemd_report(commands["systemctl"])
    missing = [name for name, path in commands.items() if path is None]
    return {
        "ok": not missing and systemd["available"],
        "missing": missing,
        "commands": commands,
        "groups": {
            "core": CORE_DEPENDENCIES,
            "smb": SMB_DEPENDENCIES,
            "nfs": NFS_DEPENDENCIES,
        },
        "systemd": systemd,
    }


def systemd_report(systemctl_path: str | None = None) -> dict[str, Any]:
    systemctl_path = systemctl_path or find_executable("systemctl")
    if not systemctl_path:
        return {"available": False, "state": "missing", "message": "systemctl is not installed"}

    version_result = subprocess.run(
        [systemctl_path, "--version"],
        text=True,
        capture_output=True,
        check=False,
    )
    version_line = (version_result.stdout or version_result.stderr).splitlines()
    version = version_line[0].strip() if version_line else None

    state_result = subprocess.run(
        [systemctl_path, "--system", "is-system-running"],
        text=True,
        capture_output=True,
        check=False,
    )
    state = (state_result.stdout or state_result.stderr).strip()
    unavailable_markers = [
        "system has not been booted with systemd",
        "failed to connect to bus",
        "failed to connect to system scope bus",
        "host is down",
        "operation not permitted",
    ]
    available = not any(marker in state.lower() for marker in unavailable_markers)
    return {
        "available": available,
        "state": state or "unknown",
        "version": version,
        "returncode": state_result.returncode,
    }


def find_executable(name: str) -> str | None:
    path = shutil.which(name)
    if path:
        return path
    for directory in ["/usr/sbin", "/sbin", "/usr/local/sbin"]:
        candidate = Path(directory) / name
        if candidate.exists() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def credential_path_for(profile: MountProfile) -> Path:
    return CREDENTIAL_DIR / f"{profile.id}.cred"


def write_credentials_file(profile: MountProfile, path: Path, secret: str) -> None:
    CREDENTIAL_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    username = profile.username or ""
    lines = [f"username={username}", f"password={secret}"]
    if profile.domain:
        lines.append(f"domain={profile.domain}")
    content = "\n".join(lines) + "\n"

    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
    finally:
        os.chmod(path, 0o600)


def ensure_mountpoint(profile: MountProfile) -> None:
    mount_path = Path(profile.mount_path)
    assert_no_symlink_ancestors(mount_path)
    if mount_path.is_symlink():
        raise HelperError("invalid_path", "mount path must not be a symlink")
    if mount_path.exists() and not mount_path.is_dir():
        raise HelperError("invalid_path", "mount path exists and is not a directory")
    mount_path.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chown(mount_path, profile.created_for_uid, profile.created_for_gid)
    os.chmod(mount_path, 0o700)


def assert_no_symlink_ancestors(mount_path: Path) -> None:
    """Reject symlinks anywhere in the path so root never follows a link out of the user's tree."""
    current = mount_path.parent
    while True:
        if current.is_symlink():
            raise HelperError("invalid_path", "mount path must not contain a symlinked parent directory")
        if current.parent == current:
            break
        current = current.parent


def remove_empty_mountpoint(profile: MountProfile) -> None:
    mount_path = Path(profile.mount_path)
    try:
        mount_path.rmdir()
    except OSError:
        pass


def build_unit_bundle_for_existing(profile: MountProfile) -> UnitBundle:
    credential_path = credential_path_for(profile) if profile.type is ProfileType.SMB and smb_requires_credentials(profile) else None
    return build_unit_bundle(profile, credential_path=str(credential_path) if credential_path else None)


def write_unit_files(bundle: UnitBundle) -> None:
    for name, content in [
        (bundle.mount_unit_name, bundle.mount_unit),
        (bundle.automount_unit_name, bundle.automount_unit),
    ]:
        path = unit_path(name)
        with path.open("w", encoding="utf-8") as handle:
            handle.write(content)
        os.chmod(path, 0o644)


def activate_profile_units(profile: MountProfile, bundle: UnitBundle) -> None:
    if profile.mount_mode == MountMode.ALWAYS:
        run(["systemctl", "disable", "--now", bundle.automount_unit_name], check=False)
        if should_defer_mount_until_login(profile):
            disable_mount_unit_on_boot(bundle.mount_unit_name)
            systemctl("start", bundle.mount_unit_name)
            return
        systemctl("enable", "--now", bundle.mount_unit_name)
        return
    run(["systemctl", "disable", "--now", bundle.mount_unit_name], check=False)
    systemctl("enable", "--now", bundle.automount_unit_name)


def should_defer_mount_until_login(profile: MountProfile) -> bool:
    return profile.mount_mode == MountMode.ALWAYS and profile.type is ProfileType.SMB and smb_requires_credentials(profile)


def disable_boot_mount_for_runtime_credentials(profile: MountProfile) -> None:
    if should_defer_mount_until_login(profile):
        disable_mount_unit_on_boot(unit_name_for_path(profile.mount_path, "mount"))


def disable_mount_unit_on_boot(unit_name: str) -> None:
    run(["systemctl", "disable", unit_name], check=False)
    run(["systemctl", "reset-failed", unit_name], check=False)


def unit_path(unit_name: str) -> Path:
    return systemd_dir() / unit_name


def systemd_dir() -> Path:
    return Path(os.environ.get("EASYMOUNT_SYSTEMD_DIR", str(DEFAULT_SYSTEMD_DIR)))


def bundle_response(bundle: UnitBundle) -> dict[str, Any]:
    return {
        "mount_unit_name": bundle.mount_unit_name,
        "automount_unit_name": bundle.automount_unit_name,
        "mount_path": bundle.mount_path,
        "credential_path": bundle.credential_path,
        "mount_unit": bundle.mount_unit,
        "automount_unit": bundle.automount_unit,
    }


def systemctl(*args: str) -> subprocess.CompletedProcess[str]:
    return run(["systemctl", *args])


def systemctl_status(command: str, unit_name: str) -> str:
    result = run(["systemctl", command, unit_name], check=False)
    return "unknown" if result.returncode != 0 else result.stdout.strip()


def unmount_profile(profile: MountProfile, bundle: UnitBundle) -> None:
    stop_result = run(["systemctl", "stop", bundle.mount_unit_name], check=False)
    if stop_result.returncode != 0 and network_mount_info(profile)["mounted"]:
        fallback = run(["umount", profile.mount_path], check=False)
        if fallback.returncode != 0:
            raise HelperError("unmount_failed", unmount_error_message(stop_result, fallback))

    mount_info = network_mount_info(profile)
    if mount_info["mounted"]:
        raise HelperError(
            "unmount_failed",
            "Share is still mounted. Close files, terminals or file browser windows using it, then try again.",
        )


def unmount_error_message(
    systemctl_result: subprocess.CompletedProcess[str],
    fallback_result: subprocess.CompletedProcess[str],
) -> str:
    message = (fallback_result.stderr or fallback_result.stdout or systemctl_result.stderr or systemctl_result.stdout).strip()
    if "busy" in message.lower():
        return "Share is busy. Close files, terminals or file browser windows using it, then try again."
    return message or "Share could not be unmounted."


def network_mount_info(profile: MountProfile) -> dict[str, str | bool | None]:
    result = run(
        ["findmnt", "--target", profile.mount_path, "--noheadings", "--output", "FSTYPE,SOURCE"],
        check=False,
    )
    if result.returncode != 0:
        return {"mounted": False, "fstype": None, "source": None}

    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if not lines:
        return {"mounted": False, "fstype": None, "source": None}

    fstype, _, source = lines[0].partition(" ")
    expected = expected_fstypes(profile)
    return {
        "mounted": fstype in expected,
        "fstype": fstype,
        "source": source.strip() or None,
    }


def expected_fstypes(profile: MountProfile) -> set[str]:
    if profile.type is ProfileType.SMB:
        return {"cifs"}
    if profile.type is ProfileType.NFS:
        return {"nfs", "nfs4"}
    return set()


def is_mounted(path: str) -> bool:
    result = run(["findmnt", "--target", path], check=False)
    return result.returncode == 0


def run(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(command, text=True, capture_output=True, check=False)
    except FileNotFoundError as exc:
        raise HelperError("missing_dependency", f"missing required command: {command[0]}") from exc
    if check and result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode,
            command,
            output=result.stdout,
            stderr=result.stderr,
        )
    return result


COMMANDS = {
    "self-check": handle_self_check,
    "validate-profile": handle_validate_profile,
    "test-connection": handle_test_connection,
    "prepare-credentials": handle_prepare_credentials,
    "install-mount": handle_install_mount,
    "remove-mount": handle_remove_mount,
    "mount-now": handle_mount_now,
    "unmount-now": handle_unmount_now,
    "status": handle_status,
}


if __name__ == "__main__":
    raise SystemExit(main())
