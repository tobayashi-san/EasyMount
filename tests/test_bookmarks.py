import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET
from unittest.mock import patch

from easymount.bookmarks import BOOKMARK_NS, kde_places_path, sync_file_browser_bookmarks, sync_mountpoint_icons
from easymount.models import MountProfile, ProfileType


def profile(mount_path: str = "/home/alice/Network/NAS-Media") -> MountProfile:
    return MountProfile(
        id="nas-1234",
        type=ProfileType.SMB,
        display_name="NAS Media",
        server="nas.local",
        remote_path="media",
        mount_path=mount_path,
        created_for_uid=1000,
        created_for_gid=1000,
    )


class BookmarkTests(unittest.TestCase):
    def test_sync_adds_and_removes_gtk_and_kde_bookmarks(self) -> None:
        with tempfile.TemporaryDirectory() as config, tempfile.TemporaryDirectory() as data:
            result = sync_file_browser_bookmarks([profile()], enabled=True, config_home=config, data_home=data)
            self.assertTrue(result["gtk"])
            self.assertTrue(result["kde"])

            gtk3 = Path(config, "gtk-3.0", "bookmarks")
            gtk4 = Path(config, "gtk-4.0", "bookmarks")
            self.assertIn("file:///home/alice/Network/NAS-Media NAS Media", gtk3.read_text())
            self.assertIn("file:///home/alice/Network/NAS-Media NAS Media", gtk4.read_text())

            kde = kde_places_path(data)
            root = ET.parse(kde).getroot()
            self.assertEqual(root.find("bookmark").get("href"), "file:///home/alice/Network/NAS-Media")
            icon = root.find(f".//{{{BOOKMARK_NS}}}icon")
            self.assertIsNotNone(icon)
            self.assertEqual(icon.get("name"), "network-server")

            sync_file_browser_bookmarks([profile()], enabled=False, config_home=config, data_home=data)
            self.assertNotIn("NAS-Media", gtk3.read_text())
            self.assertIsNone(ET.parse(kde).getroot().find("bookmark"))

    def test_sync_mountpoint_icons_uses_gio_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch("easymount.bookmarks.shutil.which", return_value="/usr/bin/gio"), patch(
                "easymount.bookmarks.subprocess.run"
            ) as run:
                run.return_value.returncode = 0
                self.assertTrue(sync_mountpoint_icons([profile(tmp)], enabled=True))
                self.assertEqual(
                    run.call_args.args[0],
                    [
                        "/usr/bin/gio",
                        "set",
                        "-t",
                        "string",
                        tmp,
                        "metadata::custom-icon-name",
                        "network-server",
                    ],
                )


if __name__ == "__main__":
    unittest.main()
