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
            if code == "timeout":
                raise TimeoutError("The read operation timed out")
            if code == "offline":
                raise urllib.error.URLError(OSError("getaddrinfo failed"))
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

    def test_a_network_timeout_is_retried(self):
        self.assertEqual(self._run(["timeout", 200]), ({"ok": 1}, 2))

    def test_no_connection_ends_with_a_readable_message(self):
        for failure in ("timeout", "offline"):
            with self.assertRaises(SystemExit) as cm:
                self._run([failure] * 10)
            self.assertIn("internet connection", str(cm.exception.code))

    def test_a_404_is_not_retried(self):
        import urllib.error
        with self.assertRaises(urllib.error.HTTPError):
            self._run([404, 200])


def _cobilled(sid, name, album, date, track, disc=1):
    return {"id": sid, "type": "songs", "attributes": {
        "name": name, "albumName": album, "releaseDate": date, "trackNumber": track, "discNumber": disc,
        "artistName": "Thaiboy Digital & Bladee", "playParams": {"id": sid}, "isrc": "ISRC" + sid,
        "durationInMillis": 100000 + int(sid) * 7000, "url": f"https://music.apple.com/at/album/x/9{sid}?i={sid}"},
        "relationships": {"artists": {"data": [{"id": "1"}]}}}


class CobilledOrder(unittest.TestCase):
    """Songs from another artist's album keep that album's order (Back 2 Life: 3, 9, 10 - not A-Z)."""
    SONGS = [_cobilled("1", "3 Star Reunite", "Back 2 Life", "2022-11-18", 10),
             _cobilled("2", "All the Way", "Back 2 Life", "2022-11-18", 3),
             _cobilled("3", "The Kingdom", "Back 2 Life", "2022-11-18", 9),
             _cobilled("4", "Bonus", "Back 2 Life", "2022-11-18", 1, disc=2),
             _cobilled("5", "Zulu", "Older Album", "2020-01-01", 12)]

    def build(self, with_single=False):
        import tempfile
        from pathlib import Path
        from unittest import mock
        single_track = {"id": "9", "type": "songs", "attributes": {
            "name": "Own Single", "releaseDate": "2022-11-18", "artistName": "Bladee",
            "playParams": {"id": "9"}, "isrc": "ISRC9", "durationInMillis": 50000}}

        def fake_amp(path, **params):
            if path.endswith("/artists/1"):
                return {"data": [{"id": "1", "attributes": {"name": "Bladee"}}]}
            if path.endswith("/view/appears-on-albums"):
                return {"data": [{"id": "other"}]}
            if path.endswith("/view/singles") and with_single:
                return {"data": [{"id": "s", "attributes": {"name": "Own Single - Single", "releaseDate": "2022-11-18"}}]}
            if "/view/" in path:
                return {"data": []}
            if path.endswith("/albums") and params.get("ids") == "other":
                return {"data": [{"relationships": {"tracks": {"data": [{"id": s["id"]} for s in self.SONGS]}}}]}
            if path.endswith("/albums") and params.get("ids") == "s":
                return {"data": [{"id": "s", "relationships": {"tracks": {"data": [single_track]}}}]}
            if path.endswith("/albums"):  # the songs' own albums: not Bladee's
                return {"data": [{"id": i, "attributes": {"name": "x", "releaseDate": "2022"},
                                  "relationships": {"artists": {"data": [{"id": "2"}]}}} for i in params["ids"].split(",")]}
            if path.endswith("/songs"):
                return {"data": [s for s in self.SONGS if s["id"] in params["ids"].split(",")]}
            raise AssertionError(path)
        with tempfile.TemporaryDirectory() as d, mock.patch.object(discog, "amp", fake_amp), \
                mock.patch.object(discog, "LISTS", Path(d)):
            return [r["title"] for r in discog.build("1", "at", quiet=True)[2]]

    def test_songs_of_one_album_follow_disc_and_track_number(self):
        self.assertEqual(self.build(), ["Zulu", "All the Way", "The Kingdom", "3 Star Reunite", "Bonus"])

    def test_an_own_single_on_the_same_day_still_sorts(self):
        self.assertEqual(self.build(with_single=True),
                         ["Zulu", "All the Way", "The Kingdom", "3 Star Reunite", "Bonus", "Own Single"])
