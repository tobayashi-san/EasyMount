import json
import os
import subprocess
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

from easymount.models import MountMode, MountProfile, ProfileType, default_mount_path
from easymount.helper import (
    HelperError,
    handle_install_mount,
    handle_self_check,
    network_mount_info,
    requirements_report,
    unmount_profile,
)
from easymount.unit import build_unit_bundle


class HelperTests(unittest.TestCase):
    def profile(self) -> MountProfile:
        return MountProfile(
            id="public-1234",
            type=ProfileType.SMB,
            display_name="Public",
            server="nas.local",
            remote_path="public",
            mount_path=default_mount_path("Public"),
            created_for_uid=os.getuid(),
            created_for_gid=os.getgid(),
        )

    def test_install_mount_dry_run_returns_units(self) -> None:
        profile = MountProfile(
            id="nas-1234",
            type=ProfileType.SMB,
            display_name="NAS",
            server="nas.local",
            remote_path="media",
            mount_path=default_mount_path("NAS"),
            created_for_uid=os.getuid(),
            created_for_gid=os.getgid(),
            username="alice",
            password_saved=True,
        )
        result = subprocess.run(
            [sys.executable, "-B", "-m", "easymount.helper", "install-mount", "--dry-run"],
            input=json.dumps({"profile": profile.to_dict(), "secret": "pw"}),
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["ok"])
        self.assertIn("mount_unit", payload)
        self.assertIn("automount_unit", payload)
        self.assertNotIn("pw", payload["mount_unit"])

    def test_install_mount_dry_run_allows_guest_smb(self) -> None:
        profile = self.profile()
        result = subprocess.run(
            [sys.executable, "-B", "-m", "easymount.helper", "install-mount", "--dry-run"],
            input=json.dumps({"profile": profile.to_dict()}),
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["ok"])
        self.assertIn("guest", payload["mount_unit"])
        self.assertNotIn("credentials=", payload["mount_unit"])

    def test_test_connection_dry_run_reports_dependencies(self) -> None:
        result = subprocess.run(
            [sys.executable, "-B", "-m", "easymount.helper", "test-connection", "--dry-run"],
            input=json.dumps({"profile": self.profile().to_dict()}),
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["probe"], "dry-run")
        self.assertIn("mount.cifs", payload["dependencies"])

    def test_self_check_does_not_require_profile(self) -> None:
        with patch("easymount.helper.requirements_report", return_value={"ok": True, "missing": []}):
            payload = handle_self_check(Namespace(dry_run=False), {})
        self.assertIn("version", payload)
        self.assertIn("runtime_dir", payload)
        self.assertEqual(payload["requirements"], {"ok": True, "missing": []})

    def test_requirements_report_groups_missing_tools(self) -> None:
        def find(name: str) -> str | None:
            return None if name == "mount.nfs" else f"/usr/bin/{name}"

        with patch("easymount.helper.find_executable", side_effect=find), patch(
            "easymount.helper.systemd_report", return_value={"available": True, "state": "running"}
        ):
            payload = requirements_report()
        self.assertFalse(payload["ok"])
        self.assertIn("mount.nfs", payload["missing"])
        self.assertIn("nfs", payload["groups"])

    def test_status_does_not_count_systemd_autofs_as_mounted(self) -> None:
        completed = subprocess.CompletedProcess(
            ["findmnt"],
            0,
            stdout="autofs systemd-1\n",
            stderr="",
        )
        with patch("easymount.helper.run", return_value=completed):
            info = network_mount_info(self.profile())
        self.assertFalse(info["mounted"])
        self.assertEqual(info["fstype"], "autofs")

    def test_status_counts_cifs_as_mounted(self) -> None:
        completed = subprocess.CompletedProcess(
            ["findmnt"],
            0,
            stdout="cifs //nas.local/public\n",
            stderr="",
        )
        with patch("easymount.helper.run", return_value=completed):
            info = network_mount_info(self.profile())
        self.assertTrue(info["mounted"])
        self.assertEqual(info["source"], "//nas.local/public")

    def test_unmount_busy_error_is_actionable(self) -> None:
        profile = self.profile()
        bundle = build_unit_bundle(profile)
        stop_result = subprocess.CompletedProcess(["systemctl"], 1, stdout="", stderr="stop failed")
        findmnt_result = subprocess.CompletedProcess(["findmnt"], 0, stdout="cifs //nas.local/public\n", stderr="")
        umount_result = subprocess.CompletedProcess(["umount"], 32, stdout="", stderr="target is busy")
        with patch("easymount.helper.run", side_effect=[stop_result, findmnt_result, umount_result]):
            with self.assertRaisesRegex(HelperError, "busy"):
                unmount_profile(profile, bundle)

    def test_install_mount_activates_mount_unit_for_always_mode(self) -> None:
        profile = self.profile()
        profile.mount_mode = MountMode.ALWAYS
        with tempfile.TemporaryDirectory() as tmp, patch("easymount.helper.require_root"), patch(
            "easymount.helper.credential_path_for", return_value=Path(tmp, "public-1234.cred")
        ), patch("easymount.helper.assert_dependencies"), patch("easymount.helper.ensure_mountpoint"), patch(
            "easymount.helper.write_unit_files"
        ), patch("easymount.helper.run", return_value=subprocess.CompletedProcess(["systemctl"], 0, "", "")) as run, patch(
            "easymount.helper.systemctl"
        ) as systemctl:
            result = handle_install_mount(Namespace(dry_run=False), {"profile": profile.to_dict()})
        self.assertTrue(result["installed"])
        run.assert_any_call(["systemctl", "disable", "--now", result["automount_unit_name"]], check=False)
        systemctl.assert_any_call("enable", "--now", result["mount_unit_name"])

    def test_install_mount_activates_automount_unit_by_default(self) -> None:
        profile = self.profile()
        with tempfile.TemporaryDirectory() as tmp, patch("easymount.helper.require_root"), patch(
            "easymount.helper.credential_path_for", return_value=Path(tmp, "public-1234.cred")
        ), patch("easymount.helper.assert_dependencies"), patch("easymount.helper.ensure_mountpoint"), patch(
            "easymount.helper.write_unit_files"
        ), patch("easymount.helper.run", return_value=subprocess.CompletedProcess(["systemctl"], 0, "", "")) as run, patch(
            "easymount.helper.systemctl"
        ) as systemctl:
            result = handle_install_mount(Namespace(dry_run=False), {"profile": profile.to_dict()})
        self.assertTrue(result["installed"])
        run.assert_any_call(["systemctl", "disable", "--now", result["mount_unit_name"]], check=False)
        systemctl.assert_any_call("enable", "--now", result["automount_unit_name"])


if __name__ == "__main__":
    unittest.main()
