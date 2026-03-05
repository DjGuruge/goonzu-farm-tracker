"""
GoonZu Farm Tracker — all-in-one launcher.

Starts the API server in a background thread and the loot scanner
in the main thread. Requires Administrator privileges (for memory access).

Build:  pyinstaller GoonZuFarm.spec
Run:    GoonZuFarm.exe   (UAC prompt will appear automatically)
"""

import sys
import os
import time
import threading
import webbrowser

# ── Multiprocessing guard (required for PyInstaller --onefile) ─────────────────
# Must be the FIRST thing in __main__ when using frozen executables.
if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()

API_HOST = "127.0.0.1"
API_PORT = 8000


def _run_api():
    """Run the FastAPI + uvicorn server in a background daemon thread."""
    import uvicorn
    from api import app  # import after freeze_support

    uvicorn.run(
        app,
        host=API_HOST,
        port=API_PORT,
        log_level="warning",
    )


def _open_browser():
    time.sleep(2.5)
    webbrowser.open(f"http://{API_HOST}:{API_PORT}")


def _banner(text: str):
    width = 52
    print("=" * width)
    print(f"  {text}")
    print("=" * width)


if __name__ == "__main__":
    _banner("GoonZu Farm Tracker")
    print()

    # ── API server ─────────────────────────────────────────────────────────────
    print("[1/2] Starting API server...")
    t_api = threading.Thread(target=_run_api, daemon=True, name="api-server")
    t_api.start()

    # ── Browser ────────────────────────────────────────────────────────────────
    t_browser = threading.Thread(target=_open_browser, daemon=True, name="browser")
    t_browser.start()

    print(f"      Dashboard → http://{API_HOST}:{API_PORT}")
    print()

    # ── Scanner (main thread — blocks until Ctrl+C) ────────────────────────────
    print("[2/2] Starting loot scanner...")
    print("      Press Ctrl+C to stop.\n")
    print("-" * 52)

    try:
        import loot_scanner
        loot_scanner.main()
    except KeyboardInterrupt:
        print("\nStopped.")
    except Exception as e:
        print(f"\n[ERROR] Scanner crashed: {e}")
        input("Press Enter to exit...")
