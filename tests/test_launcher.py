import unittest
from unittest.mock import patch

from easymount.launcher import HelperLaunchError, helper_command, helper_executable, host_helper_resolver_script


class LauncherTests(unittest.TestCase):
    def test_local_privileged_command_uses_pkexec(self) -> None:
        with patch("easymount.launcher.is_flatpak", return_value=False), patch(
            "easymount.launcher.helper_executable", return_value="/usr/libexec/easymount-helper"
        ), patch("easymount.launcher.os.geteuid", return_value=1000), patch(
            "easymount.launcher.shutil.which", return_value="/usr/bin/pkexec"
        ):
            self.assertEqual(
                helper_command("install-mount", privileged=True),
                ["/usr/bin/pkexec", "/usr/libexec/easymount-helper", "install-mount"],
            )

    def test_flatpak_privileged_command_runs_host_pkexec(self) -> None:
        with patch("easymount.launcher.is_flatpak", return_value=True), patch(
            "easymount.launcher.helper_executable", return_value="/usr/libexec/easymount-helper"
        ), patch("easymount.launcher.os.geteuid", return_value=1000), patch(
            "easymount.launcher.shutil.which", return_value="/usr/bin/flatpak-spawn"
        ):
            self.assertEqual(
                helper_command("install-mount", privileged=True),
                ["/usr/bin/flatpak-spawn", "--host", "pkexec", "/usr/libexec/easymount-helper", "install-mount"],
            )

    def test_flatpak_unprivileged_command_resolves_helper_on_host(self) -> None:
        with patch("easymount.launcher.is_flatpak", return_value=True), patch(
            "easymount.launcher.helper_executable", return_value="/usr/libexec/easymount-helper"
        ), patch("easymount.launcher.shutil.which", return_value="/usr/bin/flatpak-spawn"):
            command = helper_command("self-check")
        self.assertEqual(command[:4], ["/usr/bin/flatpak-spawn", "--host", "/bin/sh", "-lc"])
        self.assertEqual(command[-1], "self-check")
        self.assertIn("/usr/local/libexec/easymount-helper", command[4])

    def test_local_privileged_command_reports_missing_pkexec(self) -> None:
        with patch("easymount.launcher.is_flatpak", return_value=False), patch(
            "easymount.launcher.helper_executable", return_value="easymount-helper"
        ), patch("easymount.launcher.os.geteuid", return_value=1000), patch(
            "easymount.launcher.shutil.which", return_value=None
        ):
            with self.assertRaises(HelperLaunchError):
                helper_command("install-mount", privileged=True)

    def test_flatpak_defaults_to_host_helper_path(self) -> None:
        with patch.dict("easymount.launcher.os.environ", {}, clear=True), patch(
            "easymount.launcher.is_flatpak", return_value=True
        ):
            self.assertEqual(helper_executable(), "/usr/libexec/easymount-helper")

    def test_host_helper_resolver_includes_common_install_paths(self) -> None:
        script = host_helper_resolver_script()
        self.assertIn("/usr/libexec/easymount-helper", script)
        self.assertIn("/usr/local/libexec/easymount-helper", script)


if __name__ == "__main__":
    unittest.main()
