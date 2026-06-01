import tempfile
import unittest
from pathlib import Path

from easymount.settings import AppSettings, SettingsStore, normalize_theme


class SettingsTests(unittest.TestCase):
    def test_settings_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = SettingsStore(tmp)
            store.save(AppSettings(show_in_file_browser=True))
            loaded = store.load()
            self.assertTrue(loaded.show_in_file_browser)
            self.assertEqual(loaded.theme, "system")
            self.assertEqual(Path(tmp, "settings.json").stat().st_mode & 0o777, 0o600)

    def test_theme_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = SettingsStore(tmp)
            store.save(AppSettings(theme="light"))
            self.assertEqual(store.load().theme, "light")

    def test_normalize_theme(self) -> None:
        self.assertEqual(normalize_theme("dark"), "dark")
        self.assertEqual(normalize_theme("light"), "light")
        self.assertEqual(normalize_theme("unexpected"), "system")


if __name__ == "__main__":
    unittest.main()
