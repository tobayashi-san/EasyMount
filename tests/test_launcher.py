import unittest
from unittest.mock import patch

from easymount.launcher import HelperLaunchError, helper_command, helper_executable


class LauncherTests(unittest.TestCase):
    def test_local_privileged_command_uses_pkexec(self) -> None:
        with patch("easymount.launcher.helper_executable", return_value="/usr/libexec/easymount-helper"), patch(
            "easymount.launcher.os.geteuid", return_value=1000
        ), patch(
            "easymount.launcher.shutil.which", return_value="/usr/bin/pkexec"
        ):
            self.assertEqual(
                helper_command("install-mount", privileged=True),
                ["/usr/bin/pkexec", "/usr/libexec/easymount-helper", "install-mount"],
            )

    def test_local_privileged_command_reports_missing_pkexec(self) -> None:
        with patch("easymount.launcher.helper_executable", return_value="easymount-helper"), patch(
            "easymount.launcher.os.geteuid", return_value=1000
        ), patch(
            "easymount.launcher.shutil.which", return_value=None
        ):
            with self.assertRaises(HelperLaunchError):
                helper_command("install-mount", privileged=True)

    def test_configured_helper_env_wins(self) -> None:
        with patch.dict("easymount.launcher.os.environ", {"EASYMOUNT_HELPER": "/tmp/easymount-helper"}):
            self.assertEqual(helper_executable(), "/tmp/easymount-helper")


if __name__ == "__main__":
    unittest.main()
