import os
import unittest

from easymount.models import (
    MountMode,
    MountProfile,
    NFSVersion,
    ProfileType,
    ValidationError,
    default_mount_path,
    slugify_mount_name,
    validate_profile,
)


class ModelTests(unittest.TestCase):
    def test_slugify_mount_name(self) -> None:
        self.assertEqual(slugify_mount_name("NAS Media Share"), "NAS-Media-Share")
        self.assertEqual(slugify_mount_name("   "), "share")

    def test_default_mount_path(self) -> None:
        self.assertEqual(default_mount_path("NAS", home="/home/alice"), "/home/alice/Network/NAS")

    def test_smb_profile_validation(self) -> None:
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
        )
        validate_profile(profile, user_home=os.path.expanduser("~"))

    def test_rejects_unsafe_mount_path(self) -> None:
        profile = MountProfile(
            id="bad-1234",
            type=ProfileType.NFS,
            display_name="Bad",
            server="nas.local",
            remote_path="/export",
            mount_path="/etc",
            nfs_version=NFSVersion.V4,
        )
        with self.assertRaises(ValidationError):
            validate_profile(profile, user_home=os.path.expanduser("~"))

    def test_rejects_smb_server_filesystem_path_with_hint(self) -> None:
        profile = MountProfile(
            id="nas-1234",
            type=ProfileType.SMB,
            display_name="NAS",
            server="nas.local",
            remote_path="/volume1/test",
            mount_path=default_mount_path("NAS"),
        )
        with self.assertRaisesRegex(ValidationError, "exported share name"):
            validate_profile(profile, user_home=os.path.expanduser("~"))

    def test_rejects_display_name_with_control_characters(self) -> None:
        profile = MountProfile(
            id="nas-1234",
            type=ProfileType.SMB,
            display_name="NAS\nWhat=//evil/share",
            server="nas.local",
            remote_path="media",
            mount_path=default_mount_path("NAS"),
            created_for_uid=os.getuid(),
            created_for_gid=os.getgid(),
        )
        with self.assertRaisesRegex(ValidationError, "control characters"):
            validate_profile(profile, user_home=os.path.expanduser("~"))

    def test_mount_mode_defaults_to_automount_and_serializes(self) -> None:
        profile = MountProfile.from_dict(
            {
                "id": "nas-1234",
                "type": "smb",
                "display_name": "NAS",
                "server": "nas.local",
                "remote_path": "media",
                "mount_path": default_mount_path("NAS"),
            }
        )
        self.assertIs(profile.mount_mode, MountMode.AUTOMOUNT)

        profile.mount_mode = MountMode.ALWAYS
        self.assertEqual(profile.to_dict()["mount_mode"], "always")


if __name__ == "__main__":
    unittest.main()
