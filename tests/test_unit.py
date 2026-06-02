import os
import unittest

from easymount.models import MountProfile, NFSVersion, ProfileType, default_mount_path
from easymount.unit import build_unit_bundle, smb_requires_credentials, systemd_escape_path, unit_name_for_path


class UnitGenerationTests(unittest.TestCase):
    def test_systemd_escape_path_escapes_hyphen(self) -> None:
        self.assertEqual(
            systemd_escape_path("/home/alice/Network/My-Share"),
            r"home-alice-Network-My\x2dShare",
        )
        self.assertEqual(unit_name_for_path("/home/alice/Network/My-Share", "mount"), r"home-alice-Network-My\x2dShare.mount")

    def test_systemd_escape_path_escapes_leading_dot(self) -> None:
        self.assertEqual(systemd_escape_path("/.hidden/share"), r"\x2ehidden-share")

    def test_smb_unit_uses_credential_file_without_password(self) -> None:
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
        bundle = build_unit_bundle(profile, credential_path="/run/easymount/credentials/nas-1234.cred")
        self.assertIn("Type=cifs", bundle.mount_unit)
        self.assertIn("credentials=/run/easymount/credentials/nas-1234.cred", bundle.mount_unit)
        self.assertNotIn("password", bundle.mount_unit.lower())

    def test_smb_guest_unit_does_not_require_credentials(self) -> None:
        profile = MountProfile(
            id="public-1234",
            type=ProfileType.SMB,
            display_name="Public",
            server="nas.local",
            remote_path="public",
            mount_path=default_mount_path("Public"),
            created_for_uid=os.getuid(),
            created_for_gid=os.getgid(),
        )
        self.assertFalse(smb_requires_credentials(profile))
        bundle = build_unit_bundle(profile)
        self.assertIn("guest", bundle.mount_unit)
        self.assertNotIn("credentials=", bundle.mount_unit)

    def test_automount_unit_does_not_wait_for_network_online(self) -> None:
        profile = MountProfile(
            id="public-1234",
            type=ProfileType.SMB,
            display_name="Public",
            server="nas.local",
            remote_path="public",
            mount_path=default_mount_path("Public"),
            created_for_uid=os.getuid(),
            created_for_gid=os.getgid(),
        )
        bundle = build_unit_bundle(profile)
        self.assertIn("After=network-online.target", bundle.mount_unit)
        self.assertNotIn("network-online.target", bundle.automount_unit)

    def test_nfs_v3_unit_contains_version_option(self) -> None:
        profile = MountProfile(
            id="nfs-1234",
            type=ProfileType.NFS,
            display_name="NFS",
            server="nas.local",
            remote_path="/export/media",
            mount_path=default_mount_path("NFS"),
            created_for_uid=os.getuid(),
            created_for_gid=os.getgid(),
            nfs_version=NFSVersion.V3,
        )
        bundle = build_unit_bundle(profile)
        self.assertIn("Type=nfs", bundle.mount_unit)
        self.assertIn("vers=3", bundle.mount_unit)
        self.assertIn("proto=tcp", bundle.mount_unit)


if __name__ == "__main__":
    unittest.main()
