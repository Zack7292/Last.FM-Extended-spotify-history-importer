#!/usr/bin/env python3
"""
Spotify history -> Last.fm importer (simple GUI, standard library only).

1. Get a free API key + secret: https://www.last.fm/api/account/create
   (the "Get a free API key" button in the app opens that page).
2. Run:  python spotify_to_lastfm.py
3. In section "2. Last.fm API key", paste the key and the shared secret and click "Save".
   They are stored only in your home folder (~/.spotify_to_lastfm.json), never in this file.
4. Click "Connect to Last.fm", then "Allow" on the website that opens.
   The session is saved, so you only do steps 3 and 4 once.
5. (Optional) Put the Spotify .json files in the same folder as this script and click
   "Split into sublists of 2000". All files are merged, listens under 30 seconds are
   dropped, and the result is written to a new "split_output" folder next to the script.
   The first part is loaded automatically for the import (import only ONE part per day:
   3,000+ scrobbles in a day = rate limited for 24 hours).
6. Choose one or more Streaming_History_*.json files (the file picker opens in
   "split_output" if it exists) and click "Import".
"""
import hashlib
import json
import os
import queue
import re
import threading
import time
import tkinter as tk
import webbrowser
from datetime import datetime, timezone, timedelta
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from urllib.parse import urlencode
from urllib.error import HTTPError
from urllib.request import Request, urlopen

API_URL = "https://ws.audioscrobbler.com/2.0/"
AUTH_URL = "https://www.last.fm/api/auth/"
CONFIG_PATH = Path.home() / ".spotify_to_lastfm.json"
BATCH_SIZE = 50  # Last.fm maximum per track.scrobble call

# JSON splitter settings
SCRIPT_DIR = Path(__file__).resolve().parent
SPLIT_DIR = SCRIPT_DIR / "split_output"  # default place the splitter writes to / the file picker opens in
SPLIT_PREFIX = "Streaming_History"
SPLIT_CHUNK_SIZE = 2000


# --------------------------------------------------------------------------- #
# Last.fm API
# --------------------------------------------------------------------------- #
class LastFmError(Exception):
    def __init__(self, code, message):
        super().__init__(f"Last.fm error {code}: {message}")
        self.code = code


def _sign(params, secret):
    raw = "".join(f"{k}{params[k]}" for k in sorted(params) if k not in ("format", "callback"))
    return hashlib.md5((raw + secret).encode("utf-8")).hexdigest()


def lastfm_call(params, secret, post=False):
    params = dict(params)
    params["api_sig"] = _sign(params, secret)
    params["format"] = "json"
    data = urlencode(params).encode("utf-8")
    req = Request(API_URL, data=data) if post else Request(f"{API_URL}?{data.decode()}")
    req.add_header("User-Agent", "spotify-to-lastfm-importer/1.0")
    try:
        with urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        if e.code == 429:
            raise LastFmError(29, "Too many requests - Last.fm is rate limiting you, wait a few minutes")
        try:
            result = json.loads(e.read().decode("utf-8"))
        except Exception:
            raise LastFmError(e.code, f"HTTP error {e.code}")
    if "error" in result:
        raise LastFmError(result["error"], result.get("message", ""))
    return result


# --------------------------------------------------------------------------- #
# Config (keeps the connection between launches)
# --------------------------------------------------------------------------- #
def load_config():
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_config(cfg):
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    try:
        os.chmod(CONFIG_PATH, 0o600)
    except OSError:
        pass


# --------------------------------------------------------------------------- #
# JSON splitter (merge all files -> drop short listens -> sublists of 2000)
# --------------------------------------------------------------------------- #
def _natural_key(path):
    # "..._2.json" sorts before "..._10.json"
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", path.name)]


def _dump_spotify_style(entries):
    # Same layout as Spotify's export: "[ {" ... "}, {" ... "} ]" with `"key" : value`
    body = ", ".join(
        json.dumps(e, indent=2, separators=(",", " : "), ensure_ascii=False)
        for e in entries
    )
    return "[ " + body + " ]"


def split_spotify_files(src_dir, out_dir, min_seconds=30, chunk_size=SPLIT_CHUNK_SIZE, log=print):
    """Merge every .json list in src_dir, drop listens shorter than min_seconds, write
    sublists of chunk_size entries to out_dir. Returns the list of written file paths."""
    src_dir, out_dir = Path(src_dir), Path(out_dir)
    entries = []
    for f in sorted(src_dir.glob("*.json"), key=_natural_key):
        try:
            with open(f, encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception as e:
            log(f"skip {f.name} ({e})")
            continue
        if not isinstance(data, list):
            log(f"skip {f.name} (not a list)")
            continue
        log(f"read {f.name}: {len(data)} entries")
        entries.extend(data)
    if not entries:
        return []

    before = len(entries)
    entries = [e for e in entries
               if isinstance(e, dict) and (e.get("ms_played") or 0) >= min_seconds * 1000]
    log(f"Filtered out {before - len(entries)} listens under {min_seconds}s")

    out_dir.mkdir(exist_ok=True)
    for old in out_dir.glob(f"{SPLIT_PREFIX}_part*.json"):  # remove leftovers of a previous split
        old.unlink()
    parts = [entries[i:i + chunk_size] for i in range(0, len(entries), chunk_size)]
    written = []
    for n, chunk in enumerate(parts, 1):
        out = out_dir / f"{SPLIT_PREFIX}_part{n:03d}.json"
        out.write_text(_dump_spotify_style(chunk), encoding="utf-8")
        written.append(str(out))
    log(f"Total kept: {len(entries)} entries -> {len(parts)} file(s) in {out_dir}")
    return written


# --------------------------------------------------------------------------- #
# Spotify file parsing
# --------------------------------------------------------------------------- #
def load_plays(paths, min_seconds=30):
    """Return (plays, skipped_count). Each play: dict(artist, track, album, timestamp)."""
    plays, skipped = [], 0
    for p in paths:
        with open(p, encoding="utf-8") as f:
            items = json.load(f)
        for it in items:
            track = it.get("master_metadata_track_name")
            artist = it.get("master_metadata_album_artist_name")
            ms = it.get("ms_played") or 0
            if not track or not artist or ms < min_seconds * 1000:
                skipped += 1  # podcasts, audiobooks, short plays
                continue
            end = datetime.strptime(it["ts"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            start = end - timedelta(milliseconds=ms)  # Last.fm wants the START time
            plays.append({
                "artist": artist,
                "track": track,
                "album": it.get("master_metadata_album_album_name") or "",
                "timestamp": int(start.timestamp()),
                "ms": ms,
            })
    plays.sort(key=lambda x: x["timestamp"])
    return plays, skipped


def redate_realistic(plays, gap=5):
    """Give the plays NEW (fake) timestamps so they play back-to-back WITHOUT overlapping,
    each lasting as long as it really did, with the last one ending a minute ago.
    Returns (plays, days_covered)."""
    end = int(time.time()) - 60
    t = end
    out = []
    for pl in reversed(plays):
        t -= max(30, pl["ms"] // 1000)  # start time of this play
        q = dict(pl)
        q["timestamp"] = t
        out.append(q)
        t -= gap
    out.reverse()
    return out, (end - out[0]["timestamp"]) / 86400


def scrobble_batch(batch, api_key, secret, session_key):
    params = {"method": "track.scrobble", "api_key": api_key, "sk": session_key}
    for i, pl in enumerate(batch):
        params[f"artist[{i}]"] = pl["artist"]
        params[f"track[{i}]"] = pl["track"]
        params[f"timestamp[{i}]"] = str(pl["timestamp"])
        if pl["album"]:
            params[f"album[{i}]"] = pl["album"]
    res = lastfm_call(params, secret, post=True)
    scr = res.get("scrobbles", {})
    attr = scr.get("@attr", {})
    items = scr.get("scrobble", [])
    if isinstance(items, dict):
        items = [items]
    reasons = {}
    for it in items:
        code = str((it.get("ignoredMessage") or {}).get("code", "0"))
        if code != "0":
            reasons[code] = reasons.get(code, 0) + 1
    return int(attr.get("accepted", 0)), int(attr.get("ignored", 0)), reasons


IGNORE_REASONS = {
    "1": "artist name filtered",
    "2": "track name filtered",
    "3": "timestamp too far in the past (Last.fm only accepts roughly the last 2 weeks)",
    "4": "timestamp too far in the future",
    "5": "daily scrobble limit exceeded",
}


def diagnose(play, key, secret, sk):
    """Yield (label, raw answer) one step at a time so a later failure never hides earlier results."""
    # Step 0: harmless read-only call, no scrobble. Checks that the key + saved login work.
    try:
        res = lastfm_call({"method": "user.getInfo", "api_key": key, "sk": sk}, secret)
        u = res.get("user", {})
        yield ("Step 0 (read-only account check)",
               f"OK - user {u.get('name')}, playcount {u.get('playcount')}")
    except Exception as e:
        yield ("Step 0 (read-only account check)", f"FAILED: {e}")
    for label, ts in (("Step 1 (play with its ORIGINAL date)", play["timestamp"]),
                      ("Step 2 (same play with the CURRENT time)", int(time.time()) - 120)):
        time.sleep(5)
        params = {"method": "track.scrobble", "api_key": key, "sk": sk,
                  "artist[0]": play["artist"], "track[0]": play["track"],
                  "timestamp[0]": str(ts)}
        if play["album"]:
            params["album[0]"] = play["album"]
        try:
            res = lastfm_call(params, secret, post=True)
            yield (label, json.dumps(res.get("scrobbles", res), ensure_ascii=False))
        except Exception as e:
            yield (label, f"FAILED: {e}")


# --------------------------------------------------------------------------- #
# GUI
# --------------------------------------------------------------------------- #
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Spotify → Last.fm importer")
        self.geometry("700x860")
        self.cfg = load_config()
        self.pending_token = None
        self.files = []
        self.split_src = SCRIPT_DIR
        self.msgs = queue.Queue()
        self.cancel_flag = threading.Event()
        self._build_ui()
        self._refresh_connection()
        self.after(100, self._poll)

    # ---- layout -------------------------------------------------------- #
    def _build_ui(self):
        pad = {"padx": 10, "pady": 5}

        spl = ttk.LabelFrame(self, text="1. Split Spotify files (optional)")
        spl.pack(fill="x", **pad)
        row = ttk.Frame(spl)
        row.pack(fill="x", **pad)
        ttk.Button(row, text="Choose folder…", command=self.choose_split_folder).pack(side="left")
        self.split_src_lbl = ttk.Label(row, text=f"Source: {self.split_src}", foreground="gray")
        self.split_src_lbl.pack(side="left", padx=10)
        row = ttk.Frame(spl)
        row.pack(fill="x", **pad)
        ttk.Label(row, text="Drop listens shorter than").pack(side="left")
        self.split_min_sec = tk.IntVar(value=30)
        ttk.Spinbox(row, from_=0, to=300, width=5, textvariable=self.split_min_sec).pack(side="left", padx=5)
        ttk.Label(row, text="seconds, then cut into sublists of").pack(side="left")
        self.split_size = tk.IntVar(value=SPLIT_CHUNK_SIZE)
        ttk.Spinbox(row, from_=1, to=100000, width=7, textvariable=self.split_size).pack(side="left", padx=5)
        row = ttk.Frame(spl)
        row.pack(fill="x", **pad)
        self.split_btn = ttk.Button(row, text="Split into sublists of 2000", command=self.start_split)
        self.split_btn.pack(side="left")
        ttk.Label(row, text=f"Output goes to: {SPLIT_DIR}", foreground="gray").pack(side="left", padx=10)

        api = ttk.LabelFrame(self, text="2. Last.fm API key")
        api.pack(fill="x", **pad)
        self.api_status_lbl = ttk.Label(api, text="", foreground="gray")
        self.api_status_lbl.pack(anchor="w", **pad)
        grid = ttk.Frame(api)
        grid.pack(fill="x", **pad)
        grid.columnconfigure(1, weight=1)
        self.key_var = tk.StringVar()
        self.secret_var = tk.StringVar()
        ttk.Label(grid, text="API key").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=2)
        ttk.Entry(grid, textvariable=self.key_var).grid(row=0, column=1, sticky="ew", pady=2)
        ttk.Label(grid, text="Shared secret").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=2)
        ttk.Entry(grid, textvariable=self.secret_var, show="\u2022").grid(row=1, column=1, sticky="ew", pady=2)
        row = ttk.Frame(api)
        row.pack(fill="x", **pad)
        ttk.Button(row, text="Get a free API key", command=self.open_api_page).pack(side="left", padx=(0, 6))
        self.save_api_btn = ttk.Button(row, text="Save", command=self.save_api)
        self.remove_api_btn = ttk.Button(row, text="Remove", command=self.remove_api)
        self.save_api_btn.pack(side="left", padx=(0, 6))
        self.remove_api_btn.pack(side="left")

        acct = ttk.LabelFrame(self, text="3. Last.fm connection")
        acct.pack(fill="x", **pad)
        btns = ttk.Frame(acct)
        btns.pack(fill="x", **pad)
        self.connect_btn = ttk.Button(btns, text="Connect to Last.fm", command=self.start_connect)
        self.disconnect_btn = ttk.Button(btns, text="Disconnect", command=self.disconnect)
        self.connect_btn.pack(side="left", padx=(0, 6))
        self.disconnect_btn.pack(side="left")
        self.status_lbl = ttk.Label(acct, text="", foreground="gray")
        self.status_lbl.pack(anchor="w", **pad)

        imp = ttk.LabelFrame(self, text="4. Spotify file(s)")
        imp.pack(fill="x", **pad)
        row = ttk.Frame(imp)
        row.pack(fill="x", **pad)
        ttk.Button(row, text="Choose file(s)…", command=self.choose_files).pack(side="left")
        self.file_lbl = ttk.Label(row, text="No file selected", foreground="gray")
        self.file_lbl.pack(side="left", padx=10)

        opt = ttk.Frame(imp)
        opt.pack(fill="x", **pad)
        ttk.Label(opt, text="Ignore plays shorter than").pack(side="left")
        self.min_sec = tk.IntVar(value=30)
        ttk.Spinbox(opt, from_=0, to=300, width=5, textvariable=self.min_sec,
                    command=self._update_summary).pack(side="left", padx=5)
        ttk.Label(opt, text="seconds").pack(side="left")
        self.min_sec.trace_add("write", lambda *_: self._update_summary())
        ttk.Label(imp, text="Dates: plays are placed back-to-back over the last few days, with no overlap.\n"
                            "(Original dates are not kept.)", foreground="gray").pack(anchor="w", padx=10)
        self.summary_lbl = ttk.Label(imp, text="", foreground="gray")
        self.summary_lbl.pack(anchor="w", **pad)

        run = ttk.LabelFrame(self, text="5. Import")
        run.pack(fill="both", expand=True, **pad)
        row = ttk.Frame(run)
        row.pack(fill="x", **pad)
        self.import_btn = ttk.Button(row, text="Import to Last.fm", command=self.start_import)
        self.cancel_btn = ttk.Button(row, text="Cancel", command=self.cancel_flag.set, state="disabled")
        self.test_btn = ttk.Button(row, text="Test with 1 play", command=self.start_test)
        self.import_btn.pack(side="left")
        self.cancel_btn.pack(side="left", padx=6)
        self.test_btn.pack(side="left")
        self.progress = ttk.Progressbar(run, mode="determinate")
        self.progress.pack(fill="x", **pad)
        self.log = tk.Text(run, height=12, state="disabled", wrap="word")
        self.log.pack(fill="both", expand=True, **pad)

    # ---- helpers ------------------------------------------------------- #
    def write_log(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _creds(self):
        return self.cfg.get("api_key", ""), self.cfg.get("api_secret", "")

    def _refresh_connection(self):
        key, secret = self._creds()
        has_creds = bool(key and secret)
        if has_creds:
            self.api_status_lbl.config(text=f"\u2714 API key saved (ends with ...{key[-4:]})",
                                       foreground="green")
        else:
            self.api_status_lbl.config(text="No API key yet. Click \u201cGet a free API key\u201d, "
                                            "then paste the key and secret below and Save.",
                                       foreground="gray")
        self.remove_api_btn.config(state="normal" if has_creds else "disabled")

        connected = bool(self.cfg.get("session_key"))
        if connected:
            self.status_lbl.config(text=f"\u2714 Connected as {self.cfg.get('username', '?')}",
                                   foreground="green")
        elif has_creds:
            self.status_lbl.config(text="Not connected", foreground="gray")
        else:
            self.status_lbl.config(text="Save your API key first (section 2).", foreground="gray")
        self.connect_btn.config(state="normal" if (has_creds and not connected) else "disabled",
                                text="Connect to Last.fm")
        self.disconnect_btn.config(state="normal" if connected else "disabled")

    # ---- connection ---------------------------------------------------- #
    def open_api_page(self):
        webbrowser.open("https://www.last.fm/api/account/create")
        messagebox.showinfo(
            "Get a free API key",
            "A Last.fm page just opened. Enter any application name (e.g. 'My Spotify import') "
            "and a short description, then submit.\n\n"
            "Copy the API key and the Shared secret it shows you and paste them into the two "
            "boxes in this window, then click Save.")

    def save_api(self):
        key = self.key_var.get().strip()
        secret = self.secret_var.get().strip()
        if not key or not secret:
            messagebox.showwarning("Missing value", "Paste both the API key and the Shared secret.")
            return
        try:  # quick check that the pair is valid (read-only, nothing is sent to your account)
            lastfm_call({"method": "auth.getToken", "api_key": key}, secret)
        except Exception as e:
            messagebox.showerror("Error", f"{e}\n\nCheck that the API key and Shared secret are "
                                          "correct and have no extra spaces.")
            return
        if key != self.cfg.get("api_key"):  # a login belongs to one key, so start fresh
            self.cfg.pop("session_key", None)
            self.cfg.pop("username", None)
        self.cfg.update({"api_key": key, "api_secret": secret})
        save_config(self.cfg)
        self.key_var.set("")
        self.secret_var.set("")
        self._refresh_connection()
        self.write_log("API key saved. You can now click \u201cConnect to Last.fm\u201d.")

    def remove_api(self):
        if not messagebox.askyesno("Remove API key",
                                   "Remove the saved API key and secret? You will also be disconnected "
                                   "from Last.fm."):
            return
        for k in ("api_key", "api_secret", "session_key", "username"):
            self.cfg.pop(k, None)
        save_config(self.cfg)
        self._refresh_connection()

    def start_connect(self):
        key, secret = self._creds()
        if not (key and secret):
            messagebox.showwarning("No API key", "Save your Last.fm API key and secret first (section 2).")
            return
        try:
            token = lastfm_call({"method": "auth.getToken", "api_key": key}, secret)["token"]
        except Exception as e:
            messagebox.showerror("Error", f"{e}\n\nCheck your API key and secret in section 2.")
            return
        webbrowser.open(f"{AUTH_URL}?{urlencode({'api_key': key, 'token': token})}")
        self.connect_btn.config(state="disabled", text="Waiting for authorization…")
        self.status_lbl.config(text="Click \u201cYes, allow access\u201d on the Last.fm page that just opened…",
                               foreground="gray")
        threading.Thread(target=self._wait_for_auth, args=(key, secret, token), daemon=True).start()

    def _wait_for_auth(self, key, secret, token):
        """Poll Last.fm until the user clicks Allow in the browser (max 5 minutes)."""
        deadline = time.time() + 300
        while time.time() < deadline:
            try:
                res = lastfm_call({"method": "auth.getSession", "api_key": key, "token": token}, secret)
                self.msgs.put(("connected", {"session_key": res["session"]["key"],
                                             "username": res["session"]["name"]}))
                return
            except LastFmError as e:
                if e.code == 14:  # token not authorized yet
                    time.sleep(3)
                    continue
                self.msgs.put(("connect_failed", str(e)))
                return
            except Exception:
                time.sleep(3)  # temporary network problem
        self.msgs.put(("connect_failed", "Timed out waiting for authorization. Click Connect to try again."))

    def disconnect(self):
        self.cfg.pop("session_key", None)
        self.cfg.pop("username", None)
        save_config(self.cfg)
        self._refresh_connection()

    # ---- splitting ----------------------------------------------------- #
    def choose_split_folder(self):
        folder = filedialog.askdirectory(title="Folder with the Spotify .json files",
                                         initialdir=str(self.split_src))
        if folder:
            self.split_src = Path(folder)
            self.split_src_lbl.config(text=f"Source: {self.split_src}")

    def _int_var(self, var, default):
        try:
            return max(0, int(var.get()))
        except (tk.TclError, ValueError):
            return default

    def start_split(self):
        size = self._int_var(self.split_size, SPLIT_CHUNK_SIZE) or SPLIT_CHUNK_SIZE
        min_sec = self._int_var(self.split_min_sec, 30)
        self.split_btn.config(state="disabled")
        self.write_log(f"Splitting files from {self.split_src} …")
        threading.Thread(target=self._split_worker, args=(self.split_src, min_sec, size),
                         daemon=True).start()

    def _split_worker(self, src, min_sec, size):
        try:
            written = split_spotify_files(src, SPLIT_DIR, min_sec, size,
                                          log=lambda m: self.msgs.put(("log", m)))
            self.msgs.put(("split_done", written))
        except Exception as e:
            self.msgs.put(("log", f"Split failed: {e}"))
            self.msgs.put(("split_done", []))

    def _set_files(self, paths):
        self.files = list(paths)
        names = ", ".join(Path(p).name for p in self.files)
        self.file_lbl.config(text=names if len(names) < 60 else f"{len(self.files)} files selected",
                             foreground="black")
        self._update_summary()

    # ---- file selection ------------------------------------------------ #
    def choose_files(self):
        paths = filedialog.askopenfilenames(
            title="Select Spotify streaming history file(s)",
            initialdir=str(SPLIT_DIR if SPLIT_DIR.is_dir() else SCRIPT_DIR),
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")])
        if paths:
            self._set_files(paths)

    def _update_summary(self):
        if not self.files:
            return
        try:
            plays, skipped = load_plays(self.files, self._min_seconds())
        except Exception as e:
            self.summary_lbl.config(text=f"Could not read file: {e}", foreground="red")
            return
        if plays:
            first = datetime.fromtimestamp(plays[0]["timestamp"], timezone.utc).date()
            last = datetime.fromtimestamp(plays[-1]["timestamp"], timezone.utc).date()
            self.summary_lbl.config(
                text=f"{len(plays)} tracks to import ({first} → {last}), {skipped} skipped",
                foreground="black")
        else:
            self.summary_lbl.config(text=f"Nothing to import ({skipped} skipped)", foreground="red")

    def _min_seconds(self):
        try:
            return max(0, int(self.min_sec.get()))
        except (tk.TclError, ValueError):
            return 30

    # ---- import -------------------------------------------------------- #
    def start_import(self):
        if not self.cfg.get("session_key"):
            messagebox.showwarning("Not connected", "Connect to Last.fm first.")
            return
        if not self.files:
            messagebox.showwarning("No file", "Choose at least one Spotify JSON file.")
            return
        try:
            plays, _ = load_plays(self.files, self._min_seconds())
        except Exception as e:
            messagebox.showerror("Error", f"Could not read file: {e}")
            return
        if not plays:
            messagebox.showinfo("Nothing to do", "No valid plays found.")
            return
        msg = f"Scrobble {len(plays)} tracks to {self.cfg.get('username')}'s Last.fm account?"
        plays, days_cov = redate_realistic(plays)
        if days_cov > 13:
            messagebox.showerror(
                "Too long for one import",
                f"These plays add up to {days_cov:.1f} days of listening, but Last.fm only accepts "
                "roughly the last 2 weeks. Choose a smaller file and import in parts.")
            return
        msg += (f"\n\nThe ORIGINAL dates will NOT be kept: the plays will be placed back-to-back over the "
                f"last {days_cov:.1f} days. Last.fm cannot bulk-delete scrobbles, so this is hard to undo, "
                "and plays you already imported earlier will be duplicated.")
        if len(plays) > 2800:
            msg += (f"\n\nNote: {len(plays)} plays is more than Last.fm's daily limit (about 2,800 per day), "
                    "so the import will probably stop part-way.")
        if not messagebox.askyesno("Confirm", msg):
            return
        self.cancel_flag.clear()
        self.import_btn.config(state="disabled")
        self.cancel_btn.config(state="normal")
        self.progress.config(maximum=len(plays), value=0)
        threading.Thread(target=self._worker, args=(plays,), daemon=True).start()

    def start_test(self):
        if not self.cfg.get("session_key"):
            messagebox.showwarning("Not connected", "Connect to Last.fm first.")
            return
        if not self.files:
            messagebox.showwarning("No file", "Choose a Spotify JSON file first.")
            return
        plays, _ = load_plays(self.files, self._min_seconds())
        if not plays:
            messagebox.showinfo("Nothing to do", "No valid plays found.")
            return
        if not messagebox.askyesno(
                "Diagnostic test",
                f"This sends ONE track ({plays[0]['artist']} – {plays[0]['track']}) to Last.fm twice: "
                "once with its original date and once with the current time.\n\n"
                "If Last.fm accepts the second one, a single extra scrobble will appear on your profile "
                "(you can delete it there). Continue?"):
            return
        threading.Thread(target=self._test_worker, args=(plays[0],), daemon=True).start()

    def _test_worker(self, play):
        key, secret = self._creds()
        try:
            for label, raw in diagnose(play, key, secret, self.cfg["session_key"]):
                self.msgs.put(("log", f"{label}:\n  {raw}"))
        except Exception as e:
            self.msgs.put(("log", f"Test failed: {e}"))
        self.msgs.put(("log", "Test finished - copy everything above and send it to me."))

    def _worker(self, plays):
        key, secret = self._creds()
        sk = self.cfg["session_key"]
        accepted = ignored = done = 0
        for i in range(0, len(plays), BATCH_SIZE):
            if self.cancel_flag.is_set():
                self.msgs.put(("log", "Cancelled."))
                break
            batch = plays[i:i + BATCH_SIZE]
            for attempt in range(4):
                try:
                    a, ig, reasons = scrobble_batch(batch, key, secret, sk)
                    accepted += a
                    ignored += ig
                    break
                except LastFmError as e:
                    if e.code in (11, 16, 29) and attempt < 3:  # temporary / rate limit
                        wait = 60 if e.code == 29 else 10
                        self.msgs.put(("log", f"{e} – waiting {wait}s then retrying…"))
                        time.sleep(wait)
                        continue
                    self.msgs.put(("log", f"Stopped: {e}"))
                    self.msgs.put(("done", (accepted, ignored)))
                    return
                except Exception as e:
                    if attempt < 3:
                        self.msgs.put(("log", f"Network error ({e}) – retrying in 5s…"))
                        time.sleep(5)
                        continue
                    self.msgs.put(("log", f"Stopped: {e}"))
                    self.msgs.put(("done", (accepted, ignored)))
                    return
            done += len(batch)
            if a == 0 and ig > 0:
                why = ", ".join(f"{n} x {IGNORE_REASONS.get(c, 'code ' + c)}" for c, n in reasons.items())
                self.msgs.put(("log", f"Last.fm rejected the whole batch: {why or 'no reason given'}."))
                if "3" in reasons:
                    self.msgs.put(("log", "These plays are too old for the Last.fm API, so the import "
                                          "was stopped. Nothing more will be sent."))
                else:
                    self.msgs.put(("log", "Last.fm gave no further detail. Click \"Test with 1 play\" "
                                          "and send me the result."))
                self.msgs.put(("progress", done))
                self.msgs.put(("done", (accepted, ignored)))
                return
            self.msgs.put(("progress", done))
            self.msgs.put(("log", f"{done}/{len(plays)} sent "
                                  f"(accepted {accepted}, ignored {ignored})"))
            time.sleep(1.5)
        self.msgs.put(("done", (accepted, ignored)))

    def _poll(self):
        try:
            while True:
                kind, payload = self.msgs.get_nowait()
                if kind == "log":
                    self.write_log(payload)
                elif kind == "progress":
                    self.progress.config(value=payload)
                elif kind == "split_done":
                    self.split_btn.config(state="normal")
                    if payload:
                        self._set_files(payload[:1])  # one part per day: Last.fm rate limits at 3,000+/day
                        self.write_log(f"Done: {len(payload)} part(s) created. Only the first part is loaded "
                                       "for the import: import ONE part per day (3,000+ scrobbles in a day "
                                       "= rate limited for 24 hours).")
                    else:
                        self.write_log("Nothing was split (no usable .json files found).")
                elif kind == "connected":
                    self.cfg.update(payload)
                    save_config(self.cfg)
                    self._refresh_connection()
                elif kind == "connect_failed":
                    self._refresh_connection()
                    messagebox.showerror("Connection failed", payload)
                elif kind == "done":
                    acc, ign = payload
                    self.write_log(f"Finished: {acc} accepted, {ign} ignored by Last.fm.")
                    self.import_btn.config(state="normal")
                    self.cancel_btn.config(state="disabled")
        except queue.Empty:
            pass
        self.after(100, self._poll)


if __name__ == "__main__":
    App().mainloop()