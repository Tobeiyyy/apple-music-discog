"""Local website for apple-music-discog: search an artist, click, get the playlist.

    python server.py            # then open http://localhost:8766
    pythonw server.py           # same, without a console window (used for autostart)

Only listens on this computer (127.0.0.1). One job runs at a time.
"""
import contextlib
import datetime
import io
import json
import re
import sys
import threading
import traceback
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import library
import update
from discog import COUNTRY, HERE, LISTS, amp, build

PORT = 8766
STOREFRONT = COUNTRY
WEB = HERE / "web"

JOBS = {}
JOB_LOCK = threading.Lock()  # one job at a time: playlists.json and the API are shared


class _Log(io.TextIOBase):
    def __init__(self, lines):
        self.lines = lines

    def write(self, s):
        for line in s.splitlines():
            if line.strip():
                self.lines.append(line)
        return len(s)


def start_job(kind, fn):
    job = {"id": uuid.uuid4().hex[:8], "kind": kind, "status": "running", "log": [], "result": None,
           "started": datetime.datetime.now().isoformat(timespec="seconds")}
    JOBS[job["id"]] = job

    def work():
        with JOB_LOCK, contextlib.redirect_stdout(_Log(job["log"])):
            try:
                job["result"] = fn(job)
                job["status"] = "done"
            except SystemExit as e:  # our scripts use SystemExit for readable errors
                job["log"].append(str(e))
                job["status"] = "error"
            except Exception as e:
                job["log"].append(f"{type(e).__name__}: {e}")
                if sys.stderr:  # None under pythonw
                    traceback.print_exc()
                job["status"] = "error"

    threading.Thread(target=work, daemon=True).start()
    return job


def summarize(name, rows):
    releases = []
    for r in rows:
        if not releases or releases[-1]["release"] != r["release"]:
            releases.append({"release": r["release"], "date": r["release_date"], "type": r["type"], "tracks": 0})
        releases[-1]["tracks"] += 1
    secs = sum(r["duration_s"] for r in rows)
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return {"name": name, "tracks": len(rows), "duration": f"{secs // 3600}h {secs % 3600 // 60}m",
            "releases": releases, "decisions": f"/lists/{slug}-decisions.md"}


def job_preview(aid):
    def fn(job):
        print("Collecting the discography from Apple Music…")
        name, _, rows = build(aid, STOREFRONT, quiet=True)
        print(f"{len(rows)} tracks found.")
        return summarize(name, rows)
    return fn


def job_create(aid, new):
    def fn(job):
        print("Collecting the discography from Apple Music…")
        name, _, rows = build(aid, STOREFRONT, quiet=True)
        print(f"{len(rows)} tracks found.")
        pid, problems = library.write_artist(name, aid, rows, STOREFRONT, force_new=new)
        out = summarize(name, rows)
        out.update(url=f"https://music.apple.com/{STOREFRONT}/library/playlist/{pid}", problems=problems)
        return out
    return fn


def job_update(aid=None):
    def fn(job):
        print("Checking for new releases…")
        return {"report": update.run(only=aid)}
    return fn


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else (
            json.dumps(body, ensure_ascii=False) if not isinstance(body, str) else body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if u.path == "/":
                return self.send(200, (WEB / "index.html").read_bytes(), "text/html; charset=utf-8")
            if u.path == "/api/search":
                d = amp(f"/v1/catalog/{STOREFRONT}/search", term=q.get("q", ""), types="artists", limit=8)
                out = []
                for a in d.get("results", {}).get("artists", {}).get("data", []):
                    at = a["attributes"]
                    art = (at.get("artwork") or {}).get("url", "").replace("{w}", "120").replace("{h}", "120")
                    out.append({"id": a["id"], "name": at["name"], "genre": ", ".join(at.get("genreNames", [])[:2]),
                                "art": art})
                return self.send(200, out)
            if u.path == "/api/playlists":
                st = library.load_state()
                return self.send(200, [{"id": aid, "artist": p["artist"], "tracks": len(p["song_ids"]),
                                        "updated": p["updated"],
                                        "url": f'https://music.apple.com/{p["storefront"]}/library/playlist/{p["playlist_id"]}'}
                                       for aid, p in sorted(st.items(), key=lambda kv: kv[1]["artist"].lower())])
            if u.path.startswith("/api/job/"):
                job = JOBS.get(u.path.rsplit("/", 1)[-1])
                return self.send(200, job) if job else self.send(404, {"error": "unknown job"})
            if u.path.startswith("/lists/") and u.path.endswith(".md"):
                f = LISTS / u.path.rsplit("/", 1)[-1]
                if f.exists() and f.parent == LISTS:
                    return self.send(200, f.read_bytes(), "text/plain; charset=utf-8")
            return self.send(404, {"error": "not found"})
        except Exception as e:
            return self.send(500, {"error": f"{type(e).__name__}: {e}"})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        aid = str(body.get("artist_id", ""))
        if JOB_LOCK.locked():
            return self.send(409, {"error": "Another job is still running - wait a moment."})
        if self.path == "/api/preview" and aid.isdigit():
            return self.send(200, start_job("preview", job_preview(aid)))
        if self.path == "/api/create" and aid.isdigit():
            return self.send(200, start_job("create", job_create(aid, bool(body.get("new")))))
        if self.path == "/api/update":
            return self.send(200, start_job("update", job_update(aid if aid.isdigit() else None)))
        return self.send(400, {"error": "bad request"})


def main():
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"apple-music-discog running on http://localhost:{PORT}")
    srv.serve_forever()


if __name__ == "__main__":
    main()
