import unittest
from unittest.mock import patch

from easymount.secret_store import SecretServiceStore


class SecretMigrationTests(unittest.TestCase):
    def test_migrate_legacy_moves_secret_to_new_attribute(self) -> None:
        store = SecretServiceStore()
        with patch.object(SecretServiceStore, "available", return_value=True), patch.object(
            SecretServiceStore, "_lookup", side_effect=[None, "pw"]
        ), patch.object(SecretServiceStore, "store") as store_mock, patch.object(
            SecretServiceStore, "_clear"
        ) as clear_mock:
            self.assertTrue(store.migrate_legacy("nas-1234", label="NAS"))
            store_mock.assert_called_once_with("nas-1234", "pw", label="NAS")
            clear_mock.assert_called_once_with("nas-1234", "easysmb")

    def test_migrate_legacy_skips_when_new_secret_exists(self) -> None:
        store = SecretServiceStore()
        with patch.object(SecretServiceStore, "available", return_value=True), patch.object(
            SecretServiceStore, "_lookup", return_value="existing"
        ), patch.object(SecretServiceStore, "store") as store_mock:
            self.assertFalse(store.migrate_legacy("nas-1234", label="NAS"))
            store_mock.assert_not_called()

    def test_lookup_does_not_fall_back_to_legacy_attribute(self) -> None:
        store = SecretServiceStore()
        with patch.object(SecretServiceStore, "available", return_value=True), patch.object(
            SecretServiceStore, "_lookup", return_value=None
        ) as lookup_mock:
            self.assertIsNone(store.lookup("nas-1234"))
            lookup_mock.assert_called_once_with("nas-1234", "easymount")


if __name__ == "__main__":
    unittest.main()
