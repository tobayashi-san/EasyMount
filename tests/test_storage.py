import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from easymount.models import MountProfile, ProfileType
from easymount.storage import ProfileStore, default_config_dir


class StorageTests(unittest.TestCase):
    def test_loads_legacy_easysmb_profiles_when_new_config_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profile = MountProfile(
                id="legacy-1234",
                type=ProfileType.SMB,
                display_name="Legacy",
                server="nas.local",
                remote_path="media",
                mount_path="/home/alice/Network/Legacy",
                created_for_uid=1000,
                created_for_gid=1000,
            )
            legacy_dir = Path(tmp, "easysmb")
            legacy_dir.mkdir()
            legacy_dir.joinpath("profiles.json").write_text(
                json.dumps({"profiles": [profile.to_dict()]}),
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"XDG_CONFIG_HOME": tmp}):
                profiles = ProfileStore().load()
            self.assertEqual(len(profiles), 1)
            self.assertEqual(profiles[0].display_name, "Legacy")

    def test_flatpak_uses_host_config_dir_for_profiles(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch("easymount.storage.Path.home", return_value=Path(tmp)), patch(
                "easymount.storage.is_flatpak", return_value=True
            ), patch.dict(os.environ, {"XDG_CONFIG_HOME": str(Path(tmp, ".var", "app", "org.easymount.EasyMount", "config"))}):
                self.assertEqual(default_config_dir(), Path(tmp, ".config", "easymount"))


if __name__ == "__main__":
    unittest.main()
