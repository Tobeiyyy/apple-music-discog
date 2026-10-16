"""Create, verify and extend discography playlists in your Apple Music library.

Needs your Apple Music account token in .env (see README > Connect your Apple Music account):
    MEDIA_USER_TOKEN=...

playlists.json remembers which playlist belongs to which artist and which songs are already
in it, so the updater only appends what is new.

Apple's API can add songs to a library playlist but cannot reorder or remove them - fixing the
order of an existing playlist therefore always means creating a new one.
"""
import datetime
import json
import time
from pathlib import Path

from discog import amp, norm, setting

HERE = Path(__file__).parent
STATE_FILE = HERE / "playlists.json"
CHUNK = 50
FOLDER = "Artists Discogs"  # new playlists go into this library folder (top level if it doesn't exist)


def user_token():
    token = setting("MEDIA_USER_TOKEN")
    if token and token != "paste-your-media-user-token-here":
        return token
    raise SystemExit("No Apple Music account token found. Put MEDIA_USER_TOKEN=... into .env "
                     "(see README > Connect your Apple Music account).")


def save_settings(**values):
    """Write NAME=value lines into .env, keeping every other line."""
    env = HERE / ".env"
    lines = env.read_text(encoding="utf-8").splitlines() if env.exists() else []
    for name, value in values.items():
        i = next((i for i, line in enumerate(lines) if line.strip().startswith(name + "=")), None)
        if i is None:
            lines.append(f"{name}={value}")
        else:
            lines[i] = f"{name}={value}"
    env.write_text("\n".join(lines) + "\n", encoding="utf-8")


def account_country(token):
    """The account's country code ('us', 'de'…) if Apple accepts the token, else None. One try: a bad token
    should fail in a second, not after the throttling retries."""
    try:
        return amp("/v1/me/storefront", user_token=token, tries=1)["data"][0]["id"]
    except (Exception, SystemExit):
        return None


def load_state():
    return json.loads(STATE_FILE.read_text(encoding="utf-8")) if STATE_FILE.exists() else {}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _songs(ids):
    """Catalog ids are 'songs'; library ids (i.xxx, e.g. your own uploads) are 'library-songs'."""
    return [{"id": i, "type": "library-songs" if i.startswith("i.") else "songs"} for i in ids]


def folder_id(token, folder=FOLDER):
    d = amp("/v1/me/library/playlist-folders/p.playlistsroot/children?limit=100", user_token=token)
    return next((f["id"] for f in d.get("data", [])
                 if f["type"] == "library-playlist-folders" and f["attributes"].get("name") == folder), None)


def create_playlist(name, description, ids, token, folder=FOLDER):
    """folder=None creates the playlist at the top level."""
    rel = {"tracks": {"data": _songs(ids[:CHUNK])}}
    fid = folder and folder_id(token, folder)
    if fid:
        rel["parent"] = {"data": [{"id": fid, "type": "library-playlist-folders"}]}
    d = amp("/v1/me/library/playlists", method="POST", user_token=token, body={
        "attributes": {"name": name, "description": description}, "relationships": rel})
    pid = d["data"][0]["id"]
    append(pid, ids[CHUNK:], token)
    return pid


def append(pid, ids, token):
    for i in range(0, len(ids), CHUNK):
        amp(f"/v1/me/library/playlists/{pid}/tracks", method="POST", user_token=token,
            body={"data": _songs(ids[i:i + CHUNK])})
        time.sleep(1.5)


def playlist_tracks(pid, token):
    out, path = [], f"/v1/me/library/playlists/{pid}/tracks?limit=100"
    while path:
        d = amp(path, user_token=token)
        out += d.get("data", [])
        path = d.get("next")
    return out


def verify(pid, rows, token, wait=5):
    """Compare the playlist with the intended list position by position.

    Songs you already had in your library are linked as your existing library copy, which can
    have a different ID and slightly different metadata - those count as matching by title.
    Returns a list of problems (empty = playlist is exactly right).
    """
    time.sleep(wait)  # Apple needs a moment before new tracks show up
    got = playlist_tracks(pid, token)
    problems = []
    if len(got) != len(rows):
        problems.append(f"playlist has {len(got)} tracks, expected {len(rows)}")
    for i, (t, r) in enumerate(zip(got, rows), 1):
        at = t["attributes"]
        cid = (at.get("playParams") or {}).get("catalogId")
        if cid != r["apple_song_id"] and norm(at["name"])[:6] != norm(r["title"])[:6]:
            problems.append(f'#{i}: expected "{r["title"]}", playlist has "{at["name"]}"')
        if not at.get("playParams"):
            problems.append(f'#{i}: "{at["name"]}" may not be playable (your library copy has no playback info)')
    return problems


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def write_artist(name, aid, rows, sf, force_new=False):
    """Create the discography playlist for one artist and remember it in playlists.json."""
    state = load_state()
    if aid in state and not force_new:
        p = state[aid]
        raise SystemExit(f'{name} already has a playlist ({p["playlist_id"]}). Run update.py to add new '
                         f"releases, or --write --new to build a fresh one (then delete the old one yourself).")
    token = user_token()
    playlist_name = f"{name} – Discography"
    ids = [r["apple_song_id"] for r in rows]
    print(f'Creating "{playlist_name}" with {len(ids)} tracks...')
    pid = create_playlist(playlist_name, "Chronological discography, built by apple-music-discog", ids, token)
    problems = verify(pid, rows, token)
    state[aid] = {"artist": name, "storefront": sf, "playlist_id": pid, "playlist_name": playlist_name,
                  "song_ids": ids, "isrcs": [r["isrc"] for r in rows if r["isrc"]],
                  "created": _now(), "updated": _now()}
    save_state(state)
    print(f"Done: https://music.apple.com/{sf}/library/playlist/{pid}")
    print("Verified: order is exactly right." if not problems else "Check these:\n  " + "\n  ".join(problems))
    return pid, problems
