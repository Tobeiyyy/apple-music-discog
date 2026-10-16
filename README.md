# apple-music-discog

One Apple Music playlist per artist with their **whole discography in release order**: every album, EP,
single and co-billed song, each recording exactly once. A weekly updater adds new releases to the bottom.

Apple Music's own artist pages can't do this: albums, singles and deluxe editions are separate lists, the same
song shows up three times (single, album, deluxe), and clean, live and remix versions are mixed in. This tool
builds the list from Apple's catalog data and writes it into your library as a normal playlist.

Plain Python 3, no packages to install. Works with any Apple Music subscription.

> **Unofficial.** The tool talks to Apple Music the same way the music.apple.com web player does, using your
> browser's account token. Apple doesn't document or support this, rate-limits it, and could change it at any
> time. Apple's official API needs a paid Apple Developer membership. Use at your own risk.

## What ends up in the playlist

- **Releases by the artist** (albums, EPs, singles, compilations where they are the album artist), whole and
  in album order.
- **Songs on other artists' releases** when the artist is in the song's artist list (co-billed, e.g.
  "Future, Metro Boomin & Kendrick Lamar"). A "feat." only in the title doesn't count.
- **Dropped:** live recordings, DJ mixes, instrumentals, clean versions when an explicit one exists, and
  remixes/edits unless that's the only version of the song.
- **One recording appears once** (same ISRC, or same title within 5 seconds). Album beats single beats
  co-billed song. Singles that really differ (radio edits) stay.
- **Editions:** all editions of an album (original, deluxe, extended…) become one block at the original release
  date: the most complete edition in its own order, plus bonus tracks from other editions at the end.
- **Order:** release date, then albums before singles released the same day, then disc and track.

Every run also writes `lists/<artist>-decisions.md`, which lists every dropped release and track and why, so you
can check nothing you care about went missing.

## Setup

1. Install Python 3 (on Windows from [python.org](https://www.python.org/downloads/), tick "Add python.exe to
   PATH").
2. Download this repo (`git clone https://github.com/Tobeiyyy/apple-music-discog` or **Code → Download ZIP**).
3. Copy `.env.example` to `.env` and fill it in (next section).

### Get your Apple Music account token

1. Open https://music.apple.com and sign in.
2. Open the developer tools with **F12**.
   - Chrome, Edge, Brave: **Application** tab → **Cookies** → `https://music.apple.com`
   - Firefox: **Storage** tab → **Cookies** → `https://music.apple.com`
3. Copy the value of `media-user-token` and paste it into `.env`:

   ```
   MEDIA_USER_TOKEN=<the value>
   APPLE_MUSIC_COUNTRY=us
   ```

   `APPLE_MUSIC_COUNTRY` is your Apple Music country code (`us`, `gb`, `de`, `at`, `jp`…).

The token gives access to your Apple Music library: never share it or commit `.env`. It lasts for months, but
signing out of music.apple.com in that browser ends it. When it stops working, the tool says so and you repeat
these steps.

## Usage

```bash
python discog.py "Kendrick Lamar"            # build the list only -> lists/
python discog.py "Kendrick Lamar" --write    # build it and create the playlist in your library
python update.py                             # add new releases to all your playlists
python update.py --dry-run                   # show what would be added, change nothing
```

`--write` checks the finished playlist position by position. New playlists go into a library folder called
"Artists Discogs" if you have one, otherwise to the top level. `playlists.json` remembers which playlist belongs
to which artist, so `update.py` only appends what is new.

Apple's API can add songs to a playlist but can't reorder or remove them. When Apple adds an *older* release
later, the updater puts it at the bottom and tells you; for the exact order run
`python discog.py "Artist" --write --new` and delete the old playlist yourself.

### Website

`python server.py` serves a small page at http://localhost:8766 (only reachable from your computer): search an
artist, preview the list, create the playlist, check for new releases.

## Weekly updates

- **Windows:** `powershell -ExecutionPolicy Bypass -File setup-windows.ps1` registers two scheduled tasks: the
  weekly update (Fridays 12:00, or at the next logon if the PC was off) and the website at every logon.
  `-Remove` takes both away again.
- **macOS / Linux:** add a cron job (`crontab -e`):

  ```
  0 12 * * 5 cd /path/to/apple-music-discog && python3 update.py >> update-run.log 2>&1
  ```

Every update run is appended to `update-log.md`.

## Troubleshooting

- **"Apple Music rejected your account token"**: the token expired; get a new one (see above).
- **HTTP 403 after many requests**: Apple throttles busy accounts for a while. The tool already retries; if it
  still fails, wait 20 minutes and run it again. Runs only add what's missing, so repeating one is safe.
- **Wrong artist**: the search takes Apple's first match. Use the artist's Apple ID instead (the number at the
  end of their music.apple.com URL): `python discog.py 1440818847 --write`.

## Tests

```bash
python -m unittest discover -s tests
```

Developed and tested on Windows 10. macOS and Linux should work (plain Python, no Windows-only code outside
`setup-windows.ps1`), but haven't been tested yet.

## Using Spotify?

[sort-play](https://github.com/hoeci/sort-play) (a Spicetify extension) builds sorted, deduplicated discography
playlists for Spotify.

## License

MIT, see [LICENSE](LICENSE).
