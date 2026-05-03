import os
import sys
import unittest

sys.path.insert(0, os.path.abspath("src"))

from server.identity import register_device, sanitize_token


class ServerIdentityTests(unittest.TestCase):
    def setUp(self):
        self.connected_devices = {}
        self.latest_previews = {}
        self.sid_to_device = {}

    def test_sanitize_token_removes_path_chars(self):
        self.assertEqual(sanitize_token("../phone A"), "..-phone-A")

    def test_register_device_reuses_persistent_id_across_socket_ids(self):
        register_device(self.connected_devices, self.sid_to_device, self.latest_previews, "sid-1", "phone-alpha", "1.2.3.4")
        register_device(self.connected_devices, self.sid_to_device, self.latest_previews, "sid-2", "phone-alpha", "1.2.3.4")

        self.assertIn("phone-alpha", self.connected_devices)
        self.assertEqual(self.connected_devices["phone-alpha"]["sid"], "sid-2")


if __name__ == "__main__":
    unittest.main()
