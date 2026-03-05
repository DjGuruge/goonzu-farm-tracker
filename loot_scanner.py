"""
GoonZu Loot Scanner
Scans process memory for loot drop messages, prints to terminal, saves to SQLite.
"""

import re
import time
import ctypes
import ctypes.wintypes
import sqlite3
from collections import Counter
from datetime import datetime, timezone

import pymem
import pymem.process

# ── Config ────────────────────────────────────────────────────────────────────
PROCESS_NAME  = "GoonZu.exe"
DB_NAME       = "goonzu_farm.db"
SCAN_INTERVAL = 1.0    # seconds between scans
CHUNK_SIZE    = 4096   # bytes read per chunk

LOOT_PATTERN = re.compile(
    rb"Obtained \[([^\]]+)\] (\d+) unit\(s\)\.\(price: ([\d,\.]+)\[M\]\)"
)

# ── Windows memory region constants ───────────────────────────────────────────
MEM_COMMIT = 0x1000

class MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BaseAddress",       ctypes.c_ulonglong),
        ("AllocationBase",    ctypes.c_ulonglong),
        ("AllocationProtect", ctypes.wintypes.DWORD),
        ("RegionSize",        ctypes.c_size_t),
        ("State",             ctypes.wintypes.DWORD),
        ("Protect",           ctypes.wintypes.DWORD),
        ("Type",              ctypes.wintypes.DWORD),
    ]


# ── Database ──────────────────────────────────────────────────────────────────
def init_db(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS drops (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          TEXT    NOT NULL,
            item        TEXT    NOT NULL,
            qty         INTEGER NOT NULL,
            price_value REAL    NOT NULL
        )
    """)
    conn.commit()
    return conn


def save_drop(conn: sqlite3.Connection, ts: str, item: str, qty: int, price_value: float):
    conn.execute(
        "INSERT INTO drops (ts, item, qty, price_value) VALUES (?, ?, ?, ?)",
        (ts, item, qty, price_value),
    )
    conn.commit()


def parse_price(raw: str) -> float:
    """'3,207' → 3207.0"""
    return float(raw.replace(",", "").replace(".", ""))


# ── Memory scanning ───────────────────────────────────────────────────────────
def iter_readable_regions(handle):
    kernel32 = ctypes.windll.kernel32
    mbi      = MEMORY_BASIC_INFORMATION()
    address  = 0
    max_addr = 0x7FFFFFFF0000

    while address < max_addr:
        ret = kernel32.VirtualQueryEx(
            handle,
            ctypes.c_ulonglong(address),
            ctypes.byref(mbi),
            ctypes.sizeof(mbi),
        )
        if not ret:
            break

        if mbi.State == MEM_COMMIT and mbi.Protect & 0xFF in {0x02, 0x04, 0x20, 0x40}:
            yield mbi.BaseAddress, mbi.RegionSize

        address = mbi.BaseAddress + mbi.RegionSize


def scan_memory(pm: pymem.Pymem) -> list[bytes]:
    matches = []
    handle  = pm.process_handle

    for base, size in iter_readable_regions(handle):
        offset = 0
        while offset < size:
            chunk_len = min(CHUNK_SIZE, size - offset)
            try:
                data = pm.read_bytes(base + offset, chunk_len)
                for m in LOOT_PATTERN.finditer(data):
                    matches.append(m.group(0))
            except Exception:
                pass
            offset += chunk_len

    return matches


# ── Formatting ────────────────────────────────────────────────────────────────
def format_drop(item: str, qty: int, price_value: float, ts: str) -> str:
    total = qty * price_value
    return (
        f"[{ts}] +{qty:>5}x  {item:<30}  "
        f"unit: {price_value:>10,.0f}[M]   total: {total:>12,.0f}[M]"
    )


# ── Main loop ─────────────────────────────────────────────────────────────────
def main():
    print(f"Connecting to {PROCESS_NAME}...")
    try:
        pm = pymem.Pymem(PROCESS_NAME)
    except pymem.exception.ProcessNotFound:
        print(f"  Process '{PROCESS_NAME}' not found. Is the game running?")
        return

    conn = init_db(DB_NAME)
    print(f"  Attached to PID {pm.process_id}  |  DB: {DB_NAME}")
    print(f"  Scanning every {SCAN_INTERVAL}s\n")
    print(f"{'─'*80}")
    print(f"  TIME      QTY   ITEM                           UNIT PRICE      TOTAL VALUE")
    print(f"{'─'*80}")

    prev_counts: Counter[bytes] = Counter()

    try:
        while True:
            raw_matches = scan_memory(pm)
            curr_counts = Counter(raw_matches)

            for raw, curr in curr_counts.items():
                delta = curr - prev_counts.get(raw, 0)
                if delta <= 0:
                    continue

                m = LOOT_PATTERN.match(raw)
                if not m:
                    continue

                item        = m.group(1).decode("utf-8", errors="replace")
                qty         = int(m.group(2))
                price_value = parse_price(m.group(3).decode())
                ts          = datetime.now().strftime("%H:%M:%S")

                for _ in range(delta):
                    print(format_drop(item, qty, price_value, ts))
                    save_drop(conn, datetime.now(timezone.utc).isoformat(), item, qty, price_value)

            prev_counts = curr_counts
            time.sleep(SCAN_INTERVAL)

    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
