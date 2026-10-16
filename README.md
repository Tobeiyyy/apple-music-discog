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

## Get started

1. **Install Python 3.** Windows and Mac: [python.org/downloads](https://www.python.org/downloads/). On Windows,
   tick **"Add python.exe to PATH"** in the installer.
2. **Download this tool:** green **Code** button → **Download ZIP**, then unzip it anywhere.
3. **Start it:**
   - Windows: double-click **`Start.cmd`**.
   - Mac: double-click **`Start.command`**. If macOS refuses to open a downloaded script, open Terminal in the
     folder and run `python3 server.py --open` instead.
   - Linux: run `python3 server.py --open` in the folder.

   Your browser opens the app at http://localhost:8766. A small window stays open while it runs; close it to
   stop the app.
4. **Connect your Apple Music account** (one time). The app shows the steps: sign in on music.apple.com, press
   **F12**, copy the `media-user-token` cookie, paste it, click **Connect**. Your country is read from your
   account.
5. **Search an artist → Create playlist.** The playlist appears in your Apple Music library a moment later, on
   every device. **Preview list first** shows what would go in, and *what was merged or dropped, and why*
   lists every decision.

Artists you've made a playlist for show up under **Your playlists**, with **Check now** to add new releases.
New playlists go into a library folder called "Artists Discogs" if you have one, otherwise to the top level.

**About the token:** it stays on your computer (in the `.env` file next to the app) and is only sent to Apple.
Don't share it: it gives access to your Apple Music library. It lasts for months, but signing out of
music.apple.com in that browser ends it; the app then asks for a fresh one.

**Safety:** the app only listens on your own computer, and other websites can't send it commands.

## Advanced: command line

Everything the app does also works from a terminal in the tool's folder (`python3` on Mac/Linux):

```bash
python discog.py "Kendrick Lamar"            # build the list only -> lists/
python discog.py "Kendrick Lamar" --write    # build it and create the playlist in your library
python discog.py 1440818847 --write          # same, by Apple artist ID (the number at the end of their page URL)
python update.py                             # add new releases to all your playlists
python update.py --dry-run                   # show what would be added, change nothing
```

Without the app, put your token into `.env` yourself: copy `.env.example` to `.env` and fill in
`MEDIA_USER_TOKEN=` and your country code `APPLE_MUSIC_COUNTRY=` (`us`, `gb`, `de`…).

Every new playlist is checked position by position after writing. `playlists.json` remembers which playlist
belongs to which artist, so updates only append what is new. Apple's API can add songs to a playlist but can't
reorder them: when Apple adds an *older* release later, the updater puts it at the bottom and says so. For the
exact order, rebuild it (**Rebuild as a new playlist** in the app, or `python discog.py "Artist" --write --new`)
and delete the old playlist yourself.

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

- **"Apple Music rejected your account token"**: the token expired. Open the app and paste a fresh one.
- **HTTP 403 after many requests**: Apple throttles busy accounts for a while. The tool already retries; if it
  still fails, wait 20 minutes and run it again. Runs only add what's missing, so repeating one is safe.
- **Wrong artist** (command line): the search takes Apple's first match. Use the artist's Apple ID instead (see
  above). In the app you pick the artist from the search results yourself.

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
