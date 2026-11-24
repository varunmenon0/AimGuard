# Install and run AimGuard

The repository includes the trained inference model and built browser interface.
You supply a **64 Hz CS2 `.dem`** recording. CS2, Steam, Node.js and the original
training dataset are not required to run the application.

## 1. Get the code and exact Python version

```sh
git clone https://github.com/varunmenon0/AimGuard.git
cd AimGuard
```

The frozen detector requires **Python 3.12.10**, including that patch version.
This is part of its original runtime receipt; later 3.12 versions are rejected.
Install that version from [Python.org](https://www.python.org/downloads/release/python-31210/).

If you use [uv](https://docs.astral.sh/uv/getting-started/installation/), it can
select and obtain the exact Python version for the setup script:

```sh
uv run --python 3.12.10 --no-project scripts/setup_local.py
```

Otherwise run the setup script using your installed Python 3.12.10:

**macOS/Linux**

```sh
python3.12 scripts/setup_local.py
```

**Windows PowerShell**

```powershell
py -3.12 scripts/setup_local.py
```

Setup creates two environments: `.venv` for the pinned detector runtime and
`.ui-venv` for the interface. It installs dependencies and verifies the model,
its source checksums and its runtime. An internet connection is needed for
installation. Existing environments are checked, not overwritten or silently
upgraded. No model download or training step is necessary.

## 2. Launch

**macOS:** double-click `Launch AimGuard.command`, or use the terminal command.

**macOS/Linux**

```sh
.venv/bin/python scripts/launch_ui.py
```

**Windows PowerShell**

```powershell
.\.venv\Scripts\python.exe scripts\launch_ui.py
```

The browser opens at `http://127.0.0.1:8765` by default. Keep the launch terminal
open; **Ctrl+C** stops the application. Processing stays on your computer and
works offline after setup. The app is not exposed on your network.

## 3. Add a recording and review a player

A fresh clone has an empty replay library and history. The README screenshots
show a curated demonstration workspace; they do not ship its replay files or
saved reports.

Click **Add replay**, choose a `.dem` file or use its existing local path, select
a player and click **Analyze player**. Imported files are limited to 2 GiB.
Inspect the result, switch curve tabs, browse combat windows, or export evidence.
Choose **Analyze all players** to score the full inspected human roster in a
saved match summary, or **Analyze player** for the selected player only. See [the interface guide](LOCAL_INTERFACE.md)
for all controls, storage and troubleshooting.

## Score without the interface

From the repository root:

```sh
.venv/bin/python -m aimguard.offline_detector score artifacts/aimguard-v0.6 path/to/match.dem --steamid EXACT_STEAMID --output outputs/my-review
```

On Windows use `.\.venv\Scripts\python.exe` in place of `.venv/bin/python`.
Use a new output directory for every run. Open `outputs/my-review/result.html`.

## Check installation or troubleshoot

```sh
.venv/bin/python -m aimguard.ui_worker health artifacts/aimguard-v0.6
```

A successful check prints `"ready": true` plus the version and model checksum.
The application automatically selects this packaged model in a fresh clone.
An existing local research model at `outputs/xguardian/offline-v06/frozen` takes
precedence so established local analyses retain their original model identity.

- **Wrong Python:** rerun setup with Python 3.12.10, or the uv command above.
- **Existing environment differs:** use a fresh checkout, or move aside the old
  environment before setting up again. Do not install the broad research
  `requirements.txt` over the packaged runtime; use `requirements-runtime.txt`.
- **Interrupted setup:** if setup created a partial environment, remove only
  that newly created environment and rerun setup. Keep established research
  environments and your local data intact.
- **No compatible binary distribution:** the pinned scientific packages and
  parser require a supported 64-bit platform. Setup fails rather than compiling
  or substituting other versions. Report the platform and installation error.
- **Frozen source changed:** restore the matching repository files. Python
  files are checked out with LF endings on Windows to preserve their hashes.

For development tests, use the separate environments described in
[the interface guide](LOCAL_INTERFACE.md). The broader research environment and
the public inference runtime serve different purposes.
