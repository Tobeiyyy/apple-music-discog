import unittest

import discog


def _album(aid):
    return {"id": aid}


class OtherEditions(unittest.TestCase):
    def test_finds_deluxe_editions_of_own_albums(self):
        versions = {"faith": [_album("faith-deluxe-explicit"), _album("faith-deluxe-clean")]}
        self.assertEqual(discog.other_editions(["faith"], lambda aid: versions.get(aid, [])),
                         ["faith-deluxe-explicit", "faith-deluxe-clean"])

    def test_skips_editions_already_known(self):
        versions = {"a": [_album("b")], "b": [_album("a")]}
        self.assertEqual(discog.other_editions(["a", "b"], lambda aid: versions.get(aid, [])), [])

    def test_same_edition_reported_once(self):
        versions = {"a": [_album("x")], "b": [_album("x")]}
        self.assertEqual(discog.other_editions(["a", "b"], lambda aid: versions.get(aid, [])), ["x"])


def _edition(eid, n, rating, date="2021-07-31"):
    return {"rel": {"id": eid, "attributes": {"releaseDate": date, "contentRating": rating}}, "tracks": [{}] * n}


class MainEdition(unittest.TestCase):
    def test_more_tracks_wins(self):
        eds = [_edition("std", 20, "explicit"), _edition("deluxe", 30, "clean")]
        self.assertEqual(sorted(eds, key=discog.edition_rank)[0]["rel"]["id"], "deluxe")

    def test_explicit_beats_clean_on_a_tie_whatever_the_input_order(self):
        clean, explicit = _edition("1874288057", 30, "clean"), _edition("1835992995", 30, "explicit")
        for eds in ([clean, explicit], [explicit, clean]):
            self.assertEqual(sorted(eds, key=discog.edition_rank)[0]["rel"]["id"], "1835992995")

    def test_full_tie_is_decided_by_id_not_by_input_order(self):
        a, b = _edition("2", 30, "explicit"), _edition("1", 30, "explicit")
        self.assertEqual([sorted(x, key=discog.edition_rank)[0]["rel"]["id"] for x in ([a, b], [b, a])], ["1", "1"])


if __name__ == "__main__":
    unittest.main()


class AmpRetries(unittest.TestCase):
    def _run(self, codes):
        import io, urllib.error
        from unittest import mock
        calls = []

        def fake(req, timeout=30):
            calls.append(1)
            code = codes[len(calls) - 1]
            if code != 200:
                raise urllib.error.HTTPError(req.full_url, code, "x", {}, io.BytesIO(b""))
            return mock.MagicMock(__enter__=lambda s: io.BytesIO(b'{"ok": 1}'), __exit__=lambda *a: None)
        with mock.patch.object(discog.urllib.request, "urlopen", fake), mock.patch.object(discog.time, "sleep"), \
                mock.patch.object(discog, "_token", "dev"):
            return discog.amp("/v1/me/storefront", user_token="u"), len(calls)

    def test_apple_random_403s_on_the_account_are_retried(self):
        self.assertEqual(self._run([403, 403, 403, 200]), ({"ok": 1}, 4))

    def test_a_403_that_never_clears_still_fails(self):
        with self.assertRaises(Exception):
            self._run([403] * 10)

    def test_a_404_is_not_retried(self):
        import urllib.error
        with self.assertRaises(urllib.error.HTTPError):
            self._run([404, 200])
