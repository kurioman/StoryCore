"""Launcher: ``python -m story`` starts the local server on 127.0.0.1 and opens the browser."""
from __future__ import annotations

import argparse
import os
import socket
import threading
import time
import urllib.request
import webbrowser

import uvicorn

from .config import load_settings
from .main import create_app


def free_port(host: str, start: int) -> int:
    for port in range(start, start + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, port))
                return port
            except OSError:
                continue
    raise SystemExit(f"No free port found between {start} and {start + 49}.")


def main() -> None:
    ap = argparse.ArgumentParser(description="StoryCore")
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--data-dir", default=None, help="override the data folder (default: <project>/data)")
    args = ap.parse_args()
    if args.data_dir:
        os.environ["STORY_DATA_DIR"] = args.data_dir
    settings = load_settings()
    port = free_port(settings.host, args.port or settings.port)
    settings.port = port
    url = f"http://127.0.0.1:{port}/"
    app = create_app(settings)

    def open_when_ready() -> None:
        for _ in range(480):  # a first start on a slow PC can be long
            try:
                urllib.request.urlopen(url + "api/health", timeout=1)
                print(f"\n  StoryCore is running at {url}\n  Close this window (or press Ctrl+C) to stop it.\n")
                if not args.no_browser:
                    webbrowser.open(url)
                return
            except Exception:
                time.sleep(0.25)
        print(f"\n  Still starting. If nothing opens, try {url} in your browser.\n")

    threading.Thread(target=open_when_ready, daemon=True).start()
    # bound to loopback only; phone access (services/remote.py) opens its own listener only when asked
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
