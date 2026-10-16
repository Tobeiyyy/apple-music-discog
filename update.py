"""Append new releases to every discography playlist in playlists.json.

    python update.py            # add new songs to the bottom of each playlist
    python update.py --dry-run  # only show what would be added

Meant to run on a schedule (see README > Weekly updates). Every run is appended to update-log.md.
"""
import argparse
import datetime
import sys

import library
from discog import HERE, build


def run(dry_run=False, only=None):
    """Update all playlists (or only the artist ID `only`). Returns the report as Markdown."""
    state = library.load_state()
    if not state:
        return 'No playlists yet - create one with: python discog.py "Artist" --write\n'
    token = None if dry_run else library.user_token()

    report = []
    for aid, p in state.items():
        if only and aid != only:
            continue
        name, _, rows = build(aid, p["storefront"], quiet=True)
        known_ids, known_isrcs = set(p["song_ids"]), set(p["isrcs"])
        is_known = lambda r: r["apple_song_id"] in known_ids or (r["isrc"] and r["isrc"] in known_isrcs)
        new = [r for r in rows if not is_known(r)]
        if not new:
            report.append(f"- {name}: nothing new")
            continue

        report.append(f"- {name}: {len(new)} new track(s)" + (" (dry run, not added)" if dry_run else ""))
        report += [f'  - {r["release_date"]} · {r["title"]} [{r["release"]}]' for r in new]
        last_known = max((i for i, r in enumerate(rows) if is_known(r)), default=-1)
        older = [r for r in new if rows.index(r) < last_known]
        if older:
            report.append(f"  - ⚠ {len(older)} of these belong earlier in the timeline (Apple added an older "
                          f'release). They go to the bottom; for exact order run: python discog.py "{name}" --write --new')

        if not dry_run:
            library.append(p["playlist_id"], [r["apple_song_id"] for r in new], token)
            p["song_ids"] += [r["apple_song_id"] for r in new]
            p["isrcs"] += [r["isrc"] for r in new if r["isrc"]]
            p["updated"] = datetime.datetime.now().isoformat(timespec="seconds")
            library.save_state(state)

    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    text = f"## {stamp}{' (dry run)' if dry_run else ''}\n\n" + "\n".join(report) + "\n\n"
    with (HERE / "update-log.md").open("a", encoding="utf-8") as f:
        f.write(text)
    return text


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows console
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="show what would be added, change nothing")
    a = ap.parse_args()
    print(run(a.dry_run), end="")


if __name__ == "__main__":
    main()
