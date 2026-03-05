# GoonZu Farm Tracker

Real-time loot drop tracker for GoonZu. Reads game memory, stores drops in SQLite, and displays a live web dashboard with session management.

## Features

- **Memory scanner** — reads `GoonZu.exe` memory in real-time to capture loot drops
- **SQLite persistence** — every drop is stored with timestamp, item, qty and price
- **Web dashboard** — live feed, item summary, hourly chart (auto-refreshes every 5s)
- **Session tracking** — start/pause/resume/end farm sessions with per-session stats:
  - Total value earned
  - Average value/hour (full session)
  - Moving average/hour (last 15 min × 4)
  - Active duration (excludes paused time)
  - Per-item accumulated value chart

## Quick Start

1. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Launch everything** (double-click or run as Admin)
   ```
   start.bat
   ```
   - Opens the **API server** in a normal window
   - Opens the **scanner** in an elevated (Admin) window — required for memory access
   - Opens the **dashboard** in your browser at `http://localhost:8000`

3. **Start a session** — go to the Sessions tab and click **▶ New Session**

## Manual start

```bash
# Terminal 1 — API (normal)
python api.py

# Terminal 2 — Scanner (as Administrator)
python loot_scanner.py
```

## Project structure

```
GzAddon/
  loot_scanner.py   — memory scanner + SQLite writer
  api.py            — FastAPI backend
  start.bat         — one-click launcher
  requirements.txt
  static/
    index.html      — main dashboard (drops, summary, timeline)
    session.html    — session dashboard (stats, per-item chart)
```

## Drop regex

```
Obtained \[([^\]]+)\] (\d+) unit\(s\)\.\(price: ([\d,\.]+)\[M\]\)
```

Matches chat messages like:
```
Obtained [Pine] 57 unit(s).(price: 190[M])
```
