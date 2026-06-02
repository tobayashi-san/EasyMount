import os
import subprocess
import unittest
from unittest.mock import call, patch

from easymount.agent import main
from easymount.models import MountMode, MountProfile, NFSVersion, ProfileType, default_mount_path


class AgentTests(unittest.TestCase):
    def guest_smb_profile(self) -> MountProfile:
        profile = MountProfile(
            id="guest-1234",
            type=ProfileType.SMB,
            display_name="Guest Share",
            server="nas.local",
            remote_path="public",
            mount_path=default_mount_path("Guest Share"),
            created_for_uid=os.getuid(),
            created_for_gid=os.getgid(),
        )
        profile.mount_mode = MountMode.ALWAYS
        return profile

    def nfs_profile(self) -> MountProfile:
        profile = MountProfile(
            id="nfs-1234",
            type=ProfileType.NFS,
            display_name="NFS Share",
            server="nas.local",
            remote_path="/srv/export",
            mount_path=default_mount_path("NFS Share"),
            created_for_uid=os.getuid(),
            created_for_gid=os.getgid(),
            nfs_version=NFSVersion.V4,
        )
        profile.mount_mode = MountMode.ALWAYS
        return profile

    def authenticated_smb_profile(self, mount_mode: MountMode = MountMode.AUTOMOUNT) -> MountProfile:
        profile = MountProfile(
            id="auth-1234",
            type=ProfileType.SMB,
            display_name="Private Share",
            server="nas.local",
            remote_path="private",
            mount_path=default_mount_path("Private Share"),
            created_for_uid=os.getuid(),
            created_for_gid=os.getgid(),
            username="alice",
            password_saved=True,
        )
        profile.mount_mode = mount_mode
        return profile

    def test_agent_mounts_always_guest_smb_and_nfs_profiles_after_login(self) -> None:
        profiles = [self.guest_smb_profile(), self.nfs_profile()]
        ok = subprocess.CompletedProcess(["easymount-helper"], 0, stdout="", stderr="")
        with patch("easymount.agent.ProfileStore") as store_cls, patch("easymount.agent.SecretServiceStore"), patch(
            "easymount.agent.run_helper", return_value=ok
        ) as run_helper:
            store_cls.return_value.load.return_value = profiles

            result = main()

        self.assertEqual(result, 0)
        self.assertEqual(
            run_helper.call_args_list,
            [
                call("mount-now", {"profile": profiles[0].to_dict()}),
                call("mount-now", {"profile": profiles[1].to_dict()}),
            ],
        )

    def test_agent_prepares_credentials_for_authenticated_automount_profile(self) -> None:
        profile = self.authenticated_smb_profile()
        ok = subprocess.CompletedProcess(["easymount-helper"], 0, stdout="", stderr="")
        with patch("easymount.agent.ProfileStore") as store_cls, patch("easymount.agent.SecretServiceStore") as secret_cls, patch(
            "easymount.agent.run_helper", return_value=ok
        ) as run_helper:
            store_cls.return_value.load.return_value = [profile]
            secret_cls.return_value.lookup.return_value = "pw"

            result = main()

        self.assertEqual(result, 0)
        run_helper.assert_called_once_with(
            "prepare-credentials",
            {"profile": profile.to_dict(), "secret": "pw"},
        )

    def test_agent_prepares_credentials_before_mounting_authenticated_always_profile(self) -> None:
        profile = self.authenticated_smb_profile(MountMode.ALWAYS)
        ok = subprocess.CompletedProcess(["easymount-helper"], 0, stdout="", stderr="")
        expected_payload = {"profile": profile.to_dict(), "secret": "pw"}
        with patch("easymount.agent.ProfileStore") as store_cls, patch("easymount.agent.SecretServiceStore") as secret_cls, patch(
            "easymount.agent.run_helper", return_value=ok
        ) as run_helper:
            store_cls.return_value.load.return_value = [profile]
            secret_cls.return_value.lookup.return_value = "pw"

            result = main()

        self.assertEqual(result, 0)
        self.assertEqual(
            run_helper.call_args_list,
            [
                call("prepare-credentials", expected_payload),
                call("mount-now", expected_payload),
            ],
        )

    def test_agent_skips_disabled_profiles(self) -> None:
        profile = self.guest_smb_profile()
        profile.enabled = False
        with patch("easymount.agent.ProfileStore") as store_cls, patch("easymount.agent.SecretServiceStore"), patch(
            "easymount.agent.run_helper"
        ) as run_helper:
            store_cls.return_value.load.return_value = [profile]

            result = main()

        self.assertEqual(result, 0)
        run_helper.assert_not_called()


if __name__ == "__main__":
    unittest.main()
