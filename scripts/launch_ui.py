"""Launch the packaged local interface without changing the detector environment."""

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--no-browser", action="store_true")
    p.add_argument("--port", type=int, default=8765)
    a = p.parse_args()
    root = Path(__file__).resolve().parents[1]
    python = root / (
        ".ui-venv/Scripts/python.exe"
        if sys.platform == "win32"
        else ".ui-venv/bin/python"
    )
    engine = root / (
        ".venv/Scripts/python.exe" if sys.platform == "win32" else ".venv/bin/python"
    )
    if not engine.exists():
        raise SystemExit(
            "The detector environment is missing. Run scripts/setup_local.py with Python 3.12.10 first; see docs/INSTALL.md."
        )
    if not python.exists():
        print("Preparing the separate interface environment…", flush=True)
        subprocess.run([str(engine), "-m", "venv", str(root / ".ui-venv")], check=True)
    ready = (
        subprocess.run(
            [str(python), "-c", "import fastapi,uvicorn"],
            capture_output=True,
            check=False,
        ).returncode
        == 0
    )
    if not ready:
        print(
            "Installing local interface dependencies (first launch only)…", flush=True
        )
        subprocess.run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "-r",
                str(root / "requirements-ui.txt"),
            ],
            check=True,
        )
    port = a.port
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/api/ping", timeout=1
        ) as response:
            data = json.load(response)
        if (
            isinstance(data, dict)
            and data.get("app") == "AimGuard"
            and data.get("workspace") == str(root)
        ):
            url = f"http://127.0.0.1:{port}"
            print("AimGuard is already running: " + url)
            if not a.no_browser:
                webbrowser.open(url)
            return
    except (OSError, ValueError):
        port = a.port
    while port < a.port + 20:
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
                break
            except OSError:
                port += 1
    else:
        raise SystemExit("No available local port. Try --port 8900.")
    url = f"http://127.0.0.1:{port}"
    process = subprocess.Popen(
        [str(python), "-m", "aimguard.local_web", "--port", str(port)],
        cwd=root,
        env=dict(os.environ, PYTHONUTF8="1"),
    )
    try:
        for _ in range(180):
            if process.poll() is not None:
                raise SystemExit("The local server stopped. See the message above.")
            try:
                with urllib.request.urlopen(url + "/api/ping", timeout=0.5):
                    break
            except OSError:
                time.sleep(0.5)
        else:
            raise SystemExit("The interface is taking too long to start.")
        print(
            f"\nAimGuard is ready: {url}\nKeep this window open. Press Ctrl+C to stop.\n",
            flush=True,
        )
        if not a.no_browser:
            webbrowser.open(url)
        process.wait()
    except KeyboardInterrupt:
        print("\nClosing AimGuard…")
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    main()
