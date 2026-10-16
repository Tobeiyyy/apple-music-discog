"""Build a chronological discography tracklist for one artist from the Apple Music catalog.

Usage:
    python discog.py "Kendrick Lamar"
    python discog.py "Kendrick Lamar" --country de

Outputs (next to this script):
    <artist>.csv          the final ordered tracklist (with Apple song IDs)
    <artist>-decisions.md every release/track that was dropped, and why

Rules (no per-artist decisions):
    1. Releases BY the artist (albums, EPs, singles, compilations where they are the
       album artist) are included whole, in album order.
    2. Songs on OTHER releases are included on their own when the artist is in the
       song's artist list (co-billed, e.g. "Future, Metro Boomin & Kendrick Lamar").
       "feat. X" only in the title does not count - that song belongs to the other artist.
    3. Dropped: live recordings, DJ mixes, instrumentals, clean versions when an
       explicit one exists, and remixes/edits unless that is the only version.
    4. One recording appears once: album version beats single beats co-billed. Same
       recording = same ISRC, or same title within 5 seconds. Singles that really differ
       (radio edits, the "i" single) stay.
    5. Order: release date (deluxe editions sit at the ORIGINAL album date, bonus
       tracks at the end) -> albums before singles/co-billed songs on the same day (no spoilers) ->
       disc -> track.

Uses the public token of the music.apple.com web player (unofficial; may break if
Apple changes the site).
"""
import argparse
import sys
import csv
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
TOKEN_FILE = HERE / ".token"
LISTS = HERE / "lists"
UA = {"User-Agent": "Mozilla/5.0"}


def setting(name, default=None):
    """A value from .env (next to this script) or the environment."""
    env = HERE / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith(name + "="):
                return line.split("=", 1)[1].strip().strip('"') or default
    return os.environ.get(name, default)


COUNTRY = (setting("APPLE_MUSIC_COUNTRY") or "us").lower()  # your Apple Music storefront, e.g. us, gb, de

# Tags in (...) / [...] or after " - " that always drop a track
HARD_TAG = r"live|instrumental|karaoke|a ?cappella|acapella|mixed|sped up|slowed|commentary"
# Tags that drop a track unless it is the only version of that song
SOFT_TAG = r"remix|edit|mix|flip|rework|bootleg"
_tag = lambda words: re.compile(rf"([\(\[][^\)\]]*\b({words})\b[^\)\]]*[\)\]]|\s-\s.*\b({words})\b)", re.I)
HARD, SOFT = _tag(HARD_TAG), _tag(SOFT_TAG)
# Same title and length within this many seconds = same recording, even with a different ISRC
SAME_LENGTH_S = 5

# Release names that mark live albums, DJ mixes or radio shows (never included)
BAD_RELEASE = re.compile(r"\(DJ Mix\)|\bLive (at|from|in)\b|[\(\[]Live[\)\]]|\bVerzuz\b|\bUnplugged\b|"
                         r"\bon Apple Music\b|\bApple Music (1|Sessions|Live)\b", re.I)


# ---------- Apple Music catalog access ----------

def fetch_token():
    html = urllib.request.urlopen(urllib.request.Request("https://music.apple.com/us/browse", headers=UA)).read().decode()
    js = re.search(r'/assets/index[^"]*\.js', html).group(0)
    src = urllib.request.urlopen(urllib.request.Request("https://music.apple.com" + js, headers=UA)).read().decode()
    token = re.search(r"eyJ[\w-]{10,}\.[\w-]{10,}\.[\w-]{10,}", src).group(0)
    TOKEN_FILE.write_text(token)
    return token


_token = TOKEN_FILE.read_text().strip() if TOKEN_FILE.exists() else None


def amp(path, method="GET", body=None, user_token=None, **params):
    """Call the Apple Music API. user_token is needed for anything under /v1/me (your library)."""
    global _token
    if params:
        path += ("&" if "?" in path else "?") + urllib.parse.urlencode(params)
    for attempt in range(6):
        _token = _token or fetch_token()
        headers = {**UA, "Authorization": f"Bearer {_token}", "Origin": "https://music.apple.com"}
        if user_token:
            headers["Media-User-Token"] = user_token
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request("https://amp-api.music.apple.com" + path, data=data,
                                     headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                raw = r.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            if e.code == 401 and user_token and attempt >= 1:
                raise SystemExit("Apple Music rejected your account token (MEDIA_USER_TOKEN). "
                                 "It has probably expired - see README > Connect your Apple Music account.")
            if e.code == 401:
                _token = None  # expired -> scrape a fresh one
            elif e.code == 403 and user_token:  # Apple throttles busy accounts with random 403s for ~30 s
                time.sleep(10 * (attempt + 1))
            elif e.code == 429 or e.code >= 500:
                time.sleep(3 * (attempt + 1))
            else:
                raise
    raise RuntimeError(f"Apple Music API kept failing for {path}")


def paged(path, **params):
    try:
        out, d = [], amp(path, **params)
    except urllib.error.HTTPError as e:
        if e.code == 404:  # Apple returns 404 for an empty view (e.g. no compilations)
            return []
        raise
    out += d.get("data", [])
    while d.get("next"):
        d = amp(d["next"], **{k: v for k, v in params.items() if k != "limit"})
        out += d.get("data", [])
    return out


def batched(ids, n=100):
    ids = list(dict.fromkeys(ids))
    return [ids[i:i + n] for i in range(0, len(ids), n)]


# ---------- helpers ----------

def norm(title):
    """Comparable song key: lowercase, no brackets (feat./version tags), no punctuation."""
    t = re.sub(r"[\(\[].*?[\)\]]", "", title.lower())
    t = re.sub(r"\s+-\s+.*$", "", t)
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def original_date(release, tracks):
    """Deluxe editions carry the deluxe date; most tracks still carry the original album date."""
    dates = [t["attributes"].get("releaseDate") for t in tracks if t["attributes"].get("releaseDate")]
    if not dates:
        return release["attributes"]["releaseDate"]
    return min(set(dates), key=lambda d: (-dates.count(d), d))


def base_name(release_name):
    """Edition-independent album name: 'X (The Extended Edition)' / 'X (Deluxe)' -> 'x'."""
    t = re.sub(r"[\(\[][^\)\]]*[\)\]]", "", release_name.lower())
    t = re.sub(r"\s+-\s+(ep|single)$", "", t.strip())
    t = re.sub(r"\b(deluxe|expanded|extended|complete|collector'?s|anniversary|special|bonus|"
               r"edition|version|remaster(ed)?)\b", "", t)
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def edition_rank(o):
    """Main edition of an album = most tracks, then explicit over clean, then earliest, then id.
    Without the last three a tie (Faith (Deluxe): explicit and clean, 30 tracks each) was decided by
    Python's per-run set order, so the clean one won every other run and the album vanished."""
    a = o["rel"]["attributes"]
    return (-len(o.get("tracks", [])), a.get("contentRating") != "explicit", a["releaseDate"], o["rel"]["id"])


def other_editions(album_ids, versions_of):
    """Edition ids (deluxe, explicit/clean...) of the given albums that aren't among them yet.
    Asked per album because Apple's artist views list only one edition, and finding the others via
    'top songs' depended on what was popular that hour (Pop Smoke: 70 tracks one run, 100 the next)."""
    known, out = set(album_ids), []
    for aid in album_ids:
        for r in versions_of(aid):
            if r["id"] not in known:
                known.add(r["id"])
                out.append(r["id"])
    return out


def album_id_of(song):
    m = re.search(r"/album/[^/]+/(\d+)", song["attributes"].get("url", ""))
    return m.group(1) if m else None


def build(query, sf, quiet=False):
    """Build the ordered tracklist. Writes lists/<artist>.csv + decisions.md, returns (name, artist_id, rows)."""
    if str(query).isdigit():  # Apple artist ID (used by the updater, avoids search mix-ups)
        artist = amp(f"/v1/catalog/{sf}/artists/{query}")["data"][0]
    else:
        artist = amp(f"/v1/catalog/{sf}/search", term=query, types="artists", limit=1)["results"]["artists"]["data"][0]
    aid, name = artist["id"], artist["attributes"]["name"]
    if not quiet:
        print(f"Artist: {name} ({aid})")
    log = []  # (section, item, reason)

    # 1) The artist's own releases (Apple's curated views: one canonical edition each)
    own = {}
    for view, kind in (("full-albums", "album"), ("compilation-albums", "album"), ("singles", "single")):
        for r in paged(f"/v1/catalog/{sf}/artists/{aid}/view/{view}", limit=100):
            label = f'{r["attributes"]["releaseDate"]} · {r["attributes"]["name"]}'
            if BAD_RELEASE.search(r["attributes"]["name"]):
                log.append(("Release", label, "live album / DJ mix"))
            else:
                own[r["id"]] = {"rel": r, "kind": kind}

    def songs_of(album):
        return [t for t in album["relationships"]["tracks"]["data"] if t["type"] == "songs"]

    for chunk in batched(own, 50):
        for r in amp(f"/v1/catalog/{sf}/albums", ids=",".join(chunk), include="tracks")["data"]:
            own[r["id"]]["tracks"] = songs_of(r)

    # 2) Candidate co-billed songs: everything Apple links to the artist outside own releases
    cand_ids = [s["id"] for s in paged(f"/v1/catalog/{sf}/artists/{aid}/view/top-songs", limit=100)]
    appears = [r["id"] for r in paged(f"/v1/catalog/{sf}/artists/{aid}/view/appears-on-albums", limit=100)]
    for chunk in batched(appears, 50):
        for r in amp(f"/v1/catalog/{sf}/albums", ids=",".join(chunk), include="tracks")["data"]:
            cand_ids += [t["id"] for t in r["relationships"]["tracks"]["data"]]
    own_track_ids = {t["id"] for o in own.values() for t in o.get("tracks", [])}
    songs = []
    for chunk in batched([i for i in cand_ids if i not in own_track_ids]):
        songs += amp(f"/v1/catalog/{sf}/songs", ids=",".join(chunk), include="artists")["data"]

    # Own releases Apple leaves out of its views (extended/deluxe editions etc.):
    # any album of a candidate song whose ALBUM artist list contains the artist
    extra = {album_id_of(s) for s in songs} - set(own) - {None}
    extra |= set(other_editions([i for i, o in own.items() if o["kind"] == "album"],
                                lambda a: paged(f"/v1/catalog/{sf}/albums/{a}/view/other-versions", limit=50)))
    for chunk in batched(extra, 50):
        for r in amp(f"/v1/catalog/{sf}/albums", ids=",".join(chunk), include="tracks,artists")["data"]:
            if aid not in {x["id"] for x in r.get("relationships", {}).get("artists", {}).get("data", [])}:
                continue
            if BAD_RELEASE.search(r["attributes"]["name"]):
                log.append(("Release", f'{r["attributes"]["releaseDate"]} · {r["attributes"]["name"]}',
                            "live album / DJ mix"))
                continue
            kind = "single" if r["attributes"].get("isSingle") else "album"
            own[r["id"]] = {"rel": r, "kind": kind, "tracks": songs_of(r)}

    cobilled = []
    for s in songs:
        at = s["attributes"]
        label = f'{at["artistName"]} – {at["name"]} [{at.get("albumName", "")}]'
        artists = {x["id"] for x in s.get("relationships", {}).get("artists", {}).get("data", [])}
        if album_id_of(s) in own:
            continue
        if aid not in artists:
            log.append(("Not co-billed", label, "only featured / not in artist list"))
        elif BAD_RELEASE.search(at.get("albumName", "")):
            log.append(("Track", label, "live album / DJ mix"))
        else:
            cobilled.append(s)

    # 3) Track-level filtering. "Only version" = no clean-titled version of the song anywhere.
    everything = [t for o in own.values() for t in o.get("tracks", [])] + cobilled
    normal_versions = {norm(t["attributes"]["name"]) for t in everything
                       if not HARD.search(t["attributes"]["name"]) and not SOFT.search(t["attributes"]["name"])}
    explicit_keys = {norm(t["attributes"]["name"]) for t in everything
                     if t["attributes"].get("contentRating") != "clean"}

    def keep(t, where):
        at = t["attributes"]
        label = f'{where} → {at["name"]}'
        k = norm(at["name"])
        if not at.get("playParams"):
            log.append(("Track", label, "not streamable (pulled from Apple Music)"))
        elif HARD.search(at["name"]):
            log.append(("Track", label, "live/instrumental/DJ-mixed"))
        elif SOFT.search(at["name"]) and k in normal_versions:
            log.append(("Track", label, "remix/edit of a song that exists in its normal version"))
        elif at.get("contentRating") == "clean" and k in explicit_keys:
            log.append(("Track", label, "clean version (explicit exists)"))
        else:
            return True
        return False

    # 4) Assemble with ISRC dedupe: albums (biggest first) > singles > co-billed songs
    seen_isrc = set()
    seen_len = {}  # title key -> durations (s) already included

    def same_recording(t):
        """Same ISRC, or same title within SAME_LENGTH_S (labels sometimes re-register ISRCs)."""
        at = t["attributes"]
        secs = at.get("durationInMillis", 0) / 1000
        return at.get("isrc") in seen_isrc or any(
            abs(secs - d) <= SAME_LENGTH_S for d in seen_len.get(norm(at["name"]), []))

    def mark(t):
        at = t["attributes"]
        seen_isrc.add(at.get("isrc"))
        seen_len.setdefault(norm(at["name"]), []).append(at.get("durationInMillis", 0) / 1000)
    blocks = []  # (date, rank, sortkey, kind, release name, [tracks])

    # Albums: all editions of one album (original, deluxe, extended...) become ONE block at the
    # original release date - the most complete edition in its own order, then bonus tracks
    # from any other edition appended. Earlier albums win; a later album made only of
    # already-included recordings (best-ofs etc.) is dropped.
    groups = {}
    for o in own.values():
        if o["kind"] == "album":
            o["date"] = original_date(o["rel"], o.get("tracks", []))
            groups.setdefault(base_name(o["rel"]["attributes"]["name"]), []).append(o)
    for eds in groups.values():
        eds.sort(key=lambda o: (o["date"], -len(o.get("tracks", [])), o["rel"]["attributes"]["releaseDate"]))
    for eds in groups.values():  # group date = earliest edition
        for o in eds:
            o["date"] = min(e["date"] for e in eds)
        eds.sort(key=edition_rank)

    for eds in sorted(groups.values(), key=lambda eds: eds[0]["date"]):
        main_ed = eds[0]["rel"]["attributes"]
        ts = [t for t in eds[0].get("tracks", []) if keep(t, main_ed["name"])]
        if not ts or all(same_recording(t) for t in ts):
            log.append(("Release", f'{main_ed["releaseDate"]} · {main_ed["name"]}',
                        "no usable tracks" if not ts else "every song already included elsewhere"))
            continue
        for t in ts:
            mark(t)
        bonus = 0
        for o in eds[1:]:
            r = o["rel"]["attributes"]
            new = [t for t in o.get("tracks", []) if keep(t, r["name"]) and not same_recording(t)]
            for t in new:
                mark(t)
            ts += new
            bonus += len(new)
            log.append(("Edition", f'{r["releaseDate"]} · {r["name"]}', f'merged into "{main_ed["name"]}": '
                        + (f"{len(new)} bonus track(s) appended" if new else "no songs it doesn't already have")))
        label = main_ed["name"] + (f" (+{bonus} bonus tracks from other editions)" if bonus else "")
        blocks.append((eds[0]["date"], 0, main_ed["name"], "album", label, ts))

    for o in sorted((o for o in own.values() if o["kind"] == "single"), key=lambda o: o["rel"]["attributes"]["releaseDate"]):
        r = o["rel"]["attributes"]
        ts = []
        for t in o.get("tracks", []):
            if not keep(t, r["name"]):
                continue
            if same_recording(t):
                log.append(("Single", f'{r["releaseDate"]} · {t["attributes"]["name"]}', "same recording is on an album"))
                continue
            mark(t)
            ts.append(t)
        if ts:
            blocks.append((r["releaseDate"], 1, r["name"], "single", r["name"], ts))

    for s in sorted(cobilled, key=lambda s: s["attributes"].get("releaseDate", "")):
        at = s["attributes"]
        if not keep(s, at.get("albumName", "")):
            continue
        if same_recording(s):
            log.append(("Track", f'{at["artistName"]} – {at["name"]}', "same recording already included"))
            continue
        mark(s)
        blocks.append((at.get("releaseDate", ""), 1, at["name"], "co-billed",
                       f'{at.get("albumName", "")} ({at["artistName"]})', [s]))

    # 5) Order and write
    rows = []
    for date, _, _, kind, release, ts in sorted(blocks, key=lambda b: b[:3]):
        for t in ts:
            at = t["attributes"]
            rows.append({
                "pos": len(rows) + 1,
                "release_date": date,
                "release": release,
                "type": kind,
                "disc": at.get("discNumber", 1),
                "track": at.get("trackNumber"),
                "title": at["name"],
                "artists": at["artistName"],
                "explicit": at.get("contentRating", ""),
                "duration_s": round(at.get("durationInMillis", 0) / 1000),
                "isrc": at.get("isrc", ""),
                "apple_song_id": t["id"],
            })

    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    LISTS.mkdir(exist_ok=True)
    out = LISTS / f"{slug}.csv"
    with out.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)

    total = sum(r["duration_s"] for r in rows)
    lines = [f"# {name} — chronological discography\n",
             f"{len(rows)} tracks · {total // 3600}h {total % 3600 // 60}m · storefront {sf}\n",
             "## Included\n"]
    for date, _, _, kind, release, ts in sorted(blocks, key=lambda b: b[:3]):
        lines.append(f"- {date} — **{release}** · {kind} · {len(ts)} track{'s' * (len(ts) != 1)}")
    for section in ("Edition", "Release", "Single", "Track", "Not co-billed"):
        items = sorted({(i, r) for s, i, r in log if s == section})
        if items:
            title = "Merged editions" if section == "Edition" else f"Dropped: {section.lower()}"
            lines.append(f"\n## {title} ({len(items)})\n")
            lines += [f"- {i} — *{r}*" for i, r in items]
    (LISTS / f"{slug}-decisions.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    if not quiet:
        print(f"{len(rows)} tracks -> lists/{out.name}, decisions -> lists/{slug}-decisions.md")
    return name, aid, rows


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows console
    ap = argparse.ArgumentParser(description="Chronological discography playlists for Apple Music")
    ap.add_argument("artist")
    ap.add_argument("--country", default=COUNTRY, help=f"Apple Music storefront (default: {COUNTRY}, set APPLE_MUSIC_COUNTRY in .env)")
    ap.add_argument("--write", action="store_true", help="also create the playlist in your Apple Music library")
    ap.add_argument("--new", action="store_true", help="with --write: create a new playlist even if one exists")
    a = ap.parse_args()
    sf = a.country.lower()
    name, aid, rows = build(a.artist, sf)
    if a.write:
        import library
        library.write_artist(name, aid, rows, sf, force_new=a.new)


if __name__ == "__main__":
    main()
