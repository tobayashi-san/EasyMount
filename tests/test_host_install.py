import tempfile
import unittest
from pathlib import Path

from easymount.host_install import export_host_installer


class HostInstallTests(unittest.TestCase):
    def test_export_host_installer_contains_minimal_source_tree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            script = export_host_installer(Path(tmp, "export"))
            root = script.parent.parent
            self.assertTrue(script.exists())
            self.assertTrue(Path(root, "pyproject.toml").exists())
            self.assertTrue(Path(root, "easymount", "helper.py").exists())
            self.assertTrue(Path(root, "packaging", "polkit", "org.easymount.helper.policy").exists())
            self.assertTrue(Path(root, "packaging", "polkit", "org.easymount.helper.rules").exists())
            self.assertTrue(Path(root, "packaging", "systemd", "easymount-agent.service").exists())
            content = script.read_text(encoding="utf-8")
            self.assertIn('cp -R "${repo_dir}/easymount"', content)
            self.assertIn("PYTHONPATH=", content)
            self.assertNotIn("pip install", content)
            self.assertIn("/usr/share/polkit-1/rules.d/org.easymount.helper.rules", content)
            self.assertIn("systemctl --global enable easymount-agent.service", content)
            uninstall = Path(root, "scripts", "uninstall-host-helper.sh").read_text(encoding="utf-8")
            self.assertIn("/usr/share/polkit-1/rules.d/org.easymount.helper.rules", uninstall)
            self.assertIn("systemctl --global disable easymount-agent.service", uninstall)


if __name__ == "__main__":
    unittest.main()
