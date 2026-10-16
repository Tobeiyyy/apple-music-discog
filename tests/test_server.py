"""The website's connect-your-account flow and its guard against other websites."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import library
import server


class Allowed(unittest.TestCase):
    def test_this_computers_page_may_read_and_post(self):
        self.assertTrue(server.allowed("localhost:8766", "GET", {}))
        self.assertTrue(server.allowed("127.0.0.1:8766", "POST", {"X-Discog": "1"}))

    def test_a_post_from_another_website_is_refused(self):
        # A web page elsewhere can make the browser POST here, but can't add the custom header.
        self.assertFalse(server.allowed("localhost:8766", "POST", {}))

    def test_a_foreign_host_name_is_refused(self):
        # DNS rebinding: evil.example resolving to 127.0.0.1 still sends its own Host header.
        self.assertFalse(server.allowed("evil.example:8766", "GET", {}))
        self.assertFalse(server.allowed(None, "GET", {}))


class SaveSettings(unittest.TestCase):
    def test_replaces_the_token_and_keeps_other_lines(self):
        d = Path(tempfile.mkdtemp())
        (d / ".env").write_text("# mine\nMEDIA_USER_TOKEN=old\nOTHER=1\n", encoding="utf-8")
        with mock.patch.object(library, "HERE", d):
            library.save_settings(MEDIA_USER_TOKEN="new", APPLE_MUSIC_COUNTRY="de")
        self.assertEqual((d / ".env").read_text(encoding="utf-8"),
                         "# mine\nMEDIA_USER_TOKEN=new\nOTHER=1\nAPPLE_MUSIC_COUNTRY=de\n")

    def test_creates_the_file_when_missing(self):
        d = Path(tempfile.mkdtemp())
        with mock.patch.object(library, "HERE", d):
            library.save_settings(MEDIA_USER_TOKEN="t")
        self.assertEqual((d / ".env").read_text(encoding="utf-8"), "MEDIA_USER_TOKEN=t\n")


class AccountCountry(unittest.TestCase):
    def test_a_good_token_gives_the_accounts_country(self):
        with mock.patch.object(library, "amp", return_value={"data": [{"id": "de"}]}):
            self.assertEqual(library.account_country("t"), "de")

    def test_a_rejected_token_gives_none_after_one_try(self):
        calls = []

        def refuse(*a, **k):
            calls.append(k.get("tries"))
            raise RuntimeError("Apple Music API kept failing")
        with mock.patch.object(library, "amp", refuse):
            self.assertIsNone(library.account_country("bad"))
        self.assertEqual(calls, [1])


if __name__ == "__main__":
    unittest.main()
