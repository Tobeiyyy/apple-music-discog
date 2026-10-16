"""build() end to end against a made-up catalog (no network): ordering, edition merge and the drop rules."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import discog

A = "100"  # the artist


def song(sid, name, isrc, date="2020-01-01", secs=180, artists=(A,), artist_name="Artist", album_url="", rating="explicit",
         disc=1, track=1):
    return {"id": sid, "type": "songs", "attributes": {
        "name": name, "isrc": isrc, "releaseDate": date, "durationInMillis": secs * 1000, "artistName": artist_name,
        "contentRating": rating, "discNumber": disc, "trackNumber": track, "playParams": {"id": sid}, "url": album_url},
        "relationships": {"artists": {"data": [{"id": a} for a in artists]}}}


def album(aid, name, date, tracks, single=False, artists=(A,)):
    return {"id": aid, "type": "albums",
            "attributes": {"name": name, "releaseDate": date, "isSingle": single, "contentRating": "explicit"},
            "relationships": {"tracks": {"data": tracks}, "artists": {"data": [{"id": a} for a in artists]}}}


ALBUM = album("a1", "First Album", "2020-01-01", [song("s1", "Intro Song", "I1", track=1),
                                                  song("s2", "Big Hit", "I2", track=2),
                                                  song("s3", "Big Hit (Live)", "I3", track=3)])
DELUXE = album("a2", "First Album (Deluxe)", "2021-06-01", [song("s1d", "Intro Song", "I1", track=1),
                                                            song("s2d", "Big Hit", "I2", track=2),
                                                            song("s4", "Bonus Track", "I4", date="2021-06-01", track=3)])
SINGLE = album("a3", "Big Hit - Single", "2019-10-01", [song("s5", "Big Hit", "I2", date="2019-10-01")], single=True)
NEW_SINGLE = album("a4", "Later - Single", "2022-03-01", [song("s6", "Later", "I6", date="2022-03-01")], single=True)
COBILLED = song("c1", "Together", "C1", date="2021-01-01", artists=("200", A), artist_name="Other & Artist",
                album_url="https://music.apple.com/us/album/x/900")
FEATURED = song("c2", "Guest Verse", "C2", date="2021-02-01", artists=("300",), artist_name="Third",
                album_url="https://music.apple.com/us/album/y/901")
ALBUMS = {a["id"]: a for a in (ALBUM, DELUXE, SINGLE, NEW_SINGLE)}


def fake_amp(path, **params):
    if path.endswith(f"/artists/{A}"):
        return {"data": [{"id": A, "attributes": {"name": "Artist"}}]}
    views = {"full-albums": [ALBUM], "singles": [SINGLE, NEW_SINGLE], "top-songs": [COBILLED, FEATURED],
             "other-versions": [DELUXE]}
    for view, data in views.items():
        if path.endswith("/view/" + view):
            return {"data": data}
    if "/view/" in path:  # compilations, appears-on: none
        return {"data": []}
    if path.endswith("/albums"):
        return {"data": [ALBUMS[i] for i in params["ids"].split(",") if i in ALBUMS]}
    if path.endswith("/songs"):
        known = {s["id"]: s for s in (COBILLED, FEATURED)}
        return {"data": [known[i] for i in params["ids"].split(",") if i in known]}
    raise AssertionError("unexpected call " + path)


class Build(unittest.TestCase):
    def setUp(self):
        self.out = Path(tempfile.mkdtemp())
        with mock.patch.object(discog, "amp", fake_amp), mock.patch.object(discog, "LISTS", self.out):
            self.name, _, self.rows = discog.build(A, "us", quiet=True)
        self.titles = [r["title"] for r in self.rows]

    def test_order_is_release_date_with_deluxe_bonus_tracks_at_the_original_album(self):
        self.assertEqual(self.titles, ["Intro Song", "Big Hit", "Bonus Track", "Together", "Later"])

    def test_a_single_whose_recording_is_on_the_album_is_dropped(self):
        self.assertEqual(self.titles.count("Big Hit"), 1)
        self.assertEqual(self.rows[1]["apple_song_id"], "s2")  # the album version, not the single

    def test_live_and_featured_only_songs_are_dropped_and_explained(self):
        self.assertNotIn("Big Hit (Live)", self.titles)
        self.assertNotIn("Guest Verse", self.titles)
        decisions = (self.out / "artist-decisions.md").read_text(encoding="utf-8")
        self.assertIn("live/instrumental/DJ-mixed", decisions)
        self.assertIn("only featured / not in artist list", decisions)
        self.assertIn("same recording is on an album", decisions)

    def test_the_csv_is_written(self):
        self.assertTrue((self.out / "artist.csv").exists())


if __name__ == "__main__":
    unittest.main()
