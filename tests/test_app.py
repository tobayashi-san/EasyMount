import unittest

from easymount.app import (
    format_helper_status,
    HelperResult,
    mount_mode_from_index,
    mount_mode_index,
    mount_mode_label,
    status_css_class,
    status_text,
    theme_from_index,
    theme_index,
)
from easymount.models import MountMode


class AppTests(unittest.TestCase):
    def test_status_text_for_automount_states(self) -> None:
        self.assertEqual(status_text(HelperResult(True, {"mounted": True})), "Mounted")
        self.assertEqual(status_text(HelperResult(True, {"automount_active": "active"})), "Ready")
        self.assertEqual(status_text(HelperResult(True, {"automount_enabled": "enabled"})), "Enabled")
        self.assertEqual(
            status_text(HelperResult(True, {"mode": "always", "mount_enabled": "enabled"})),
            "Enabled",
        )
        self.assertEqual(status_text(HelperResult(True, {})), "Offline")
        self.assertEqual(status_text(HelperResult(False, {})), "Error")

    def test_status_css_classes(self) -> None:
        self.assertEqual(status_css_class("Mounted"), "status-mounted")
        self.assertEqual(status_css_class("Ready"), "status-ready")
        self.assertEqual(status_css_class("Enabled"), "status-enabled")
        self.assertEqual(status_css_class("Offline"), "status-offline")
        self.assertEqual(status_css_class("Error"), "status-error")

    def test_theme_mapping(self) -> None:
        self.assertEqual(theme_index("system"), 0)
        self.assertEqual(theme_index("light"), 1)
        self.assertEqual(theme_index("dark"), 2)
        self.assertEqual(theme_index("bad"), 0)
        self.assertEqual(theme_from_index(1), "light")
        self.assertEqual(theme_from_index(99), "system")

    def test_mount_mode_mapping(self) -> None:
        self.assertEqual(mount_mode_index(MountMode.AUTOMOUNT), 0)
        self.assertEqual(mount_mode_index(MountMode.ALWAYS), 1)
        self.assertIs(mount_mode_from_index(1), MountMode.ALWAYS)
        self.assertIs(mount_mode_from_index(99), MountMode.AUTOMOUNT)
        self.assertEqual(mount_mode_label(MountMode.ALWAYS), "Always mounted")

    def test_format_helper_status_reports_missing_requirements(self) -> None:
        text = format_helper_status(
            {
                "version": "0.1.0",
                "requirements": {
                    "missing": ["mount.nfs"],
                    "groups": {"core": ["systemctl"], "smb": ["mount.cifs"], "nfs": ["mount.nfs"]},
                    "systemd": {"available": True, "state": "running"},
                },
            },
            secret_tool_available=False,
        )
        self.assertIn("Version: 0.1.0", text)
        self.assertIn("NFS tools missing: mount.nfs", text)
        self.assertIn("secret-tool", text)


if __name__ == "__main__":
    unittest.main()
