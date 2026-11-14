# Spotify → Last.fm importer

A small Python/Tkinter desktop app that takes your Spotify extended streaming history, splits it into sublists of 2,000 tracks, and imports them into Last.fm. No extra packages needed.

---

## Table of contents

- [Spotify → Last.fm importer](#spotify--lastfm-importer)
  - [Table of contents](#table-of-contents)
  - [Read this first: the daily limit](#read-this-first-the-daily-limit)
  - [Requirements](#requirements)
  - [Installation](#installation)
    - [1. Install Python 3](#1-install-python-3)
    - [2. Get the app (choose one option)](#2-get-the-app-choose-one-option)
    - [3. Add your Spotify files](#3-add-your-spotify-files)
    - [4. Start the app](#4-start-the-app)
  - [How to use it, step by step](#how-to-use-it-step-by-step)
    - [Step 1: Get your Spotify extended streaming history](#step-1-get-your-spotify-extended-streaming-history)
    - [Step 2: Get and save your Last.fm API key (one time, free)](#step-2-get-and-save-your-lastfm-api-key-one-time-free)
    - [Step 3: Generate the JSON sublists](#step-3-generate-the-json-sublists)
    - [Step 4: Connect your Last.fm account (one time)](#step-4-connect-your-lastfm-account-one-time)
    - [Step 5: Import (one part per day!)](#step-5-import-one-part-per-day)
  - [What each section of the app does](#what-each-section-of-the-app-does)
  - [Good to know](#good-to-know)
  - [Files](#files)
  - [Windows launcher](#windows-launcher)
  - [Disclaimer](#disclaimer)

---

## Read this first: the daily limit

> ## ⚠️ DO NOT SCROBBLE 3,000 OR MORE TRACKS IN ONE DAY
>
> If you do, it **won't work** and you will be **rate limited by Last.fm for 24 hours**.
>
> That is why the history is cut into parts of **2,000** tracks: staying below 3,000 leaves you **leeway to listen to music and scrobble normally during the day** without going over.
>
> - Import **only ONE part per day**. Never two parts on the same day.
> - Your normal listening that day counts toward the same limit.

---

## Requirements

- Python 3 with Tkinter (see [Installation](#installation))
- A free Last.fm account
- Your Spotify **Extended streaming history** ([Step 1](#step-1-get-your-spotify-extended-streaming-history))
- No extra Python packages

---

## Installation

### 1. Install Python 3

- **Windows / macOS:** download it from https://www.python.org/downloads/. On Windows, tick **"Add python.exe to PATH"** during setup.
- **Linux:** Python is usually installed, but Tkinter may be missing. On Debian/Ubuntu: `sudo apt install python3 python3-tk`.
- Check that it works by running `python --version` (or `python3 --version`) in a terminal.

### 2. Get the app (choose one option)

**Option A: Download a release (easiest, no Git needed)**

1. Open the **Releases** page of this repository on GitHub (right side of the repo page).
2. Under the latest release, download the **zip** (for example "Source code (zip)").
3. Extract it to a folder of your choice.

**Option B: Download the repository as a zip**

1. On the repository's main page, click the green **Code** button, then **Download ZIP**.
2. Extract it to a folder of your choice.

**Option C: Clone with Git**

```bash
git clone https://github.com/<your-username>/<repo-name>.git
cd <repo-name>
```

(Replace `<your-username>/<repo-name>` with this repository's address.)

### 3. Add your Spotify files

> **Important:** your `Streaming_History_Audio_*.json` files **must be in the same folder as `spotify_to_lastfm.py`**. The app only looks in its own folder when splitting, so files stored anywhere else are **not detected**.

1. Copy your `Streaming_History_Audio_*.json` files ([Step 1](#step-1-get-your-spotify-extended-streaming-history)) into the folder that contains `spotify_to_lastfm.py`.
2. Put the files **directly in that folder**, not inside a subfolder. Spotify's zip often extracts into a subfolder (e.g. "Spotify Extended Streaming History"): open it and move the `.json` files out.

Your folder should look like this:

```
my-folder/
├── spotify_to_lastfm.py
├── Start_Windows.bat
├── Streaming_History_Audio_2019.json
├── Streaming_History_Audio_2020_1.json
└── ...
```

(If you prefer to keep them elsewhere, use **Choose folder…** in section 1 of the app to point it at that folder.)

### 4. Start the app

- **Windows:** double-click `Start_Windows.bat`.
- **Any system:** open a terminal in the folder and run:
  ```bash
  python spotify_to_lastfm.py
  ```
  (use `python3` on macOS/Linux if `python` isn't found)

Then follow the steps below.

---

## How to use it, step by step

### Step 1: Get your Spotify extended streaming history

1. Log in at https://www.spotify.com/account/privacy/ (Account → Privacy settings).
2. Scroll to **Download your data** and tick **Extended streaming history** (the other options are not needed).
3. Click **Request data** and confirm via the email Spotify sends you.
4. Wait. Spotify says this can take **up to 30 days**, but it often arrives sooner. You'll get an email when it's ready.
5. Download the `.zip` from the email and extract it. Inside you'll find files named `Streaming_History_Audio_*.json`. These are the ones you need.
6. Put them **directly in the same folder as `spotify_to_lastfm.py`**, otherwise the splitter won't detect them (see [Installation](#installation), part 3).

(Spotify's page may look slightly different over time, but the option is always called "Extended streaming history".)

### Step 2: Get and save your Last.fm API key (one time, free)

Last.fm requires every app to use its own key, so none is included in the script.

1. Start the app (see [Installation](#installation), part 4).
2. In section **2. Last.fm API key**, click **Get a free API key**. A Last.fm page opens (log in if asked).
3. Fill in the form: any application name (e.g. "My Spotify import"), a short description and your email. Leave the callback URL empty, then submit.
4. Copy the **API key** and the **Shared secret** it gives you.
5. Paste them into the two boxes in the app and click **Save**. The app checks they are valid and shows "API key saved".

Your key and secret are stored only on your computer, in `~/.spotify_to_lastfm.json` in your home folder, never in the script. Keep them private.

### Step 3: Generate the JSON sublists

1. Make sure your `.json` files are in the **same folder as `spotify_to_lastfm.py`** (the splitter only detects files there, unless you pick another folder with **Choose folder…**). The folder shown after "Source:" in section 1 is where it will look.
2. In section **1. Split Spotify files**, click **Split into sublists of 2000**.
3. The app merges all your `.json` files, removes listens shorter than 30 seconds, and cuts the result into parts of **2,000** entries.
4. The parts are saved in a new **`split_output`** folder next to the script, named `Streaming_History_part001.json`, `part002.json`, and so on, in the same format as the originals. The last part holds the remainder.
5. When it finishes, **only the first part** is loaded for the import (on purpose, so you can't send everything at once). Running the split again replaces the previous parts.

Your original files are never changed.

### Step 4: Connect your Last.fm account (one time)

1. In section **3. Last.fm connection**, click **Connect to Last.fm**.
2. A Last.fm page opens: click **Yes, allow access**.
3. The app shows "Connected as <your name>". The login is saved, so you won't need to do this again next time.

### Step 5: Import (one part per day!)

> **⚠️ Only ONE part (2,000 tracks) per day.** 3,000 or more scrobbles in a day will **not work** and **rate limits you for 24 hours**. The 2,000 size leaves leeway for what you listen to and scrobble during the day.

1. In section **4. Spotify file(s)**, check which file is loaded. Right after Step 3 it is `Streaming_History_part001.json`. On later days, click **Choose file(s)…** (it opens in `split_output`) and select **only the next part** (`part002`, then `part003`, ...). Never select several parts at once.
2. Optional: click **Test with 1 play** in section **5. Import** first to check that everything works.
3. Click **Import to Last.fm** and confirm. Progress shows in the window. **Cancel** stops it.
4. **Wait until the next day**, then import the next part.

Keep track of which parts you've already done. Importing the same part twice creates duplicates, and Last.fm cannot bulk-delete scrobbles.

---

## What each section of the app does

| Section | What it does |
|---|---|
| **1. Split Spotify files** | Merges the `.json` files, drops short listens, writes the 2,000-entry parts to `split_output`. You can change the minimum length and the part size. **Choose folder…** lets you split files from another folder. |
| **2. Last.fm API key** | Get, save and remove your API key and secret. |
| **3. Last.fm connection** | Connect or disconnect your Last.fm account. |
| **4. Spotify file(s)** | Choose the part to import and set the minimum play length. |
| **5. Import** | Test with 1 play, import, or cancel. |

To change your API key later, paste the new one and click **Save** (you'll need to connect again). **Remove** deletes the saved key and disconnects you.

---

## Good to know

- **Daily limit: 3,000+ scrobbles in a day = rate limited for 24 hours** (see [the warning](#read-this-first-the-daily-limit)). Stay at one 2,000-entry part per day.
- Last.fm only accepts scrobbles from roughly the last 2 weeks, so the original dates are **not kept**. Plays are placed back-to-back, ending just before the moment you import.
- Podcasts, audiobooks and entries without a track name are skipped.
- Your Spotify data is personal. Don't commit your `.json` files or the `split_output` folder to a public repository (the included `.gitignore` already excludes them).
- Sharing the script is safe: it contains no key or secret. Never share `~/.spotify_to_lastfm.json`.

---

## Files

| File | Purpose |
|---|---|
| `spotify_to_lastfm.py` | The app (splitter + importer) |
| `Start_Windows.bat` | Windows launcher: double-click to start the app without a terminal |
| `split_json.py` | Standalone splitter, optional (the app already includes it) |
| `.gitignore` | Keeps your Spotify data and generated files out of Git |

---

## Windows launcher

`Start_Windows.bat` is a tiny helper so you don't need a terminal on Windows. Double-clicking it:

1. Moves to the folder it's in, so it must stay next to `spotify_to_lastfm.py`.
2. Runs `python spotify_to_lastfm.py`.
3. If the app exits with an error, keeps the window open so you can read the message.

If nothing happens or you see "python is not recognized", Python isn't installed or isn't on your PATH: see [Installation](#installation). On macOS/Linux, use the terminal command instead.

---

## Disclaimer

This project was vibe coded with [Claude](https://claude.ai) (by Anthropic). It works for its author's use case, but it has not been audited, so use it at your own risk and keep a backup of your original data.