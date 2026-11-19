# Local replay workspace

AimGuard's interface is a local browser application around the existing frozen
v0.6 detector. It binds to `127.0.0.1`, opens in your normal browser, and processes
replay data on this computer. It contains no external analytics, fonts or CDN
dependencies. Importing a file sends it to the local application on this same
computer.

## Start and stop

On macOS, double-click `Launch AimGuard.command` in the repository folder. A
Terminal window starts the application and opens the browser. Leave that window
open while using AimGuard. Press **Ctrl+C** in that window to stop it. Closing a
browser tab does not stop the engine.

The command-line equivalent, run from the repository, is:

```sh
.venv/bin/python scripts/launch_ui.py
```

The default address is `http://127.0.0.1:8765`. An existing instance of this same
workspace is reopened rather than duplicated. If another application occupies
that port, the launcher chooses an available port and prints its actual address.
Use `--port 8900` to start searching at a different port, or `--no-browser` to
print the address without opening a tab.

The first launch installs the interface requirements into `.ui-venv`. It does
not install anything into the detector's `.venv`. Subsequent use is offline.
The checked-in `ui/dist` bundle means Node.js is not needed for normal use.

The launcher is tested on this Mac. A terminal launch on Windows uses
`.venv\Scripts\python.exe scripts\launch_ui.py`; the Windows flow has not been
tested here.

## Review a player

1. **Choose a replay.** Files under `data/` are indexed automatically. Refresh
   the library after adding files there. The count is files, not unique matches:
   separate copies of a match appear separately.
2. **Add a recording if needed.** **Add replay → Import file** copies a `.dem`
   into the local inbox. **Use local path** reads an existing file directly,
   avoiding another copy. Files must be CS2 recordings no larger than 2 GiB.
3. **Choose a player.** The app reads human Steam identities from the replay,
   including players who disconnected before the end. Short bot identifiers are
   excluded. The exact SteamID is shown alongside each name. Team labels come
   from roster metadata and are not a permanent team assignment across sides.
4. **Analyze player.** One local worker runs at a time to limit memory use.
   Progress follows artifacts actually written by the detector. Large matches
   take longer. You can leave this screen and revisit the job from history.
5. **Inspect the evidence.** The result includes usable combat-window coverage,
   boundary warnings, and signed feature contributions. The four curve tabs show
   recorded view angles, derived angular speed, horizontal opponent alignment,
   and view/opponent motion. Choose a window and hover for sample values. Time
   zero is that window's first shot; shot markers come from replay fire events.
   Rates use the detector's configured **64 Hz** assumption. Use suitable 64 Hz
   recordings; the interface does not infer an alternative tick rate.

**Review recommended** means the score crossed the frozen threshold of 75/100.
**No review flag** means it did not. **Insufficient evidence** is unresolved,
and a failed or interrupted job never becomes a negative prediction. Scores
are uncalibrated review priorities, not cheating probabilities. Opponent geometry
does not establish visibility or the player's intended target.

**Analysis history** stores new runs and imports existing compatible saved
reports. Saved reports are displayed without recomputing them; only results
matching this frozen model are imported. Analysis is for the selected player,
not every player in a match.

**Export evidence** downloads a ZIP with the prediction, tracking, event and
report artifacts, plus self-contained HTML evidence. The replay itself is not
included. **Open full evidence report** opens the detailed trajectory report in
another tab. Neither operation uploads anything.

Keyboard shortcuts: **⌘/Ctrl+O** adds a replay; **⌘/Ctrl+K** focuses library search.

## Storage and recovery

Generated interface state stays under `outputs/local-ui/`:

| Location | Contents |
| --- | --- |
| `workspace.json` | Indexed paths, inspected rosters and job history |
| `inbox/` | Recordings imported through the file picker |
| `runs/<id>/` | Individual run outputs and worker logs |
| `exports/` | Evidence ZIP files |

These files, demos, models, environments and dependencies remain ignored by Git.
The app does not modify original recordings. Replacing a recording invalidates
its cached roster. If the application stops mid-analysis, the job is marked
interrupted at the next launch; start a new review to retry it. **Cancel analysis**
stops the active worker or removes a waiting job from execution.

## Troubleshooting

- **Disconnected:** keep the launch window open and reload the displayed local
  address. If the server restarted, reloading obtains a new local session.
- **Engine needs attention:** open **Settings** for the precise model/load error.
  The original `.venv` and `outputs/xguardian/offline-v06/frozen` are required.
  Source/dependency verification failures are shown instead of bypassed. Model
  artifacts remain local and are not distributed with the GitHub repository.
- **Couldn't read a replay:** expand its error details. Use a valid CS2 `.dem`,
  check that the file still exists, and try another recording if it is damaged.
- **First launch can't install dependencies:** an internet connection is needed
  for initial setup; retry the launcher once connected.
- **Interface bundle missing:** restore the tracked `ui/dist` files or rebuild
  them using the development commands below.

## Development

The new FastAPI service uses only the separate web environment. Inspection and
scoring run as subprocesses through `.venv/bin/python`, preserving the detector's
checked Python/dependency versions. The API checks local hosts, browser origins
and a per-process session token. Reports are confined to the selected completed
run, and HTML evidence is sandboxed. The server is intended for loopback use;
there is no remote access/account system.

Install and test the web service without touching the detector environment:

```sh
.venv/bin/python -m venv .ui-venv
.ui-venv/bin/python -m pip install -r requirements-ui-dev.txt
.ui-venv/bin/python -m pytest -q ui_tests tests/test_local_store.py
.venv/bin/python -m pytest -q
```

To edit the React interface, use Node.js 24 and two terminals:

```sh
# Terminal 1, repository root
.ui-venv/bin/python -m aimguard.local_web --port 8765

# Terminal 2
cd ui
npm ci
npm run dev
```

Open the Vite address printed by terminal 2. Its API proxy points to local port
8765. Build after changes with `npm run build`; commit both `ui/src` and the
updated `ui/dist` bundle. CI rebuilds it to check that the packaged interface
matches the source, and runs the separate service tests.

Interface verification includes a browser-driven run of an already-used
development player. Its new score matched the existing result exactly, with 83
combat windows. This was a repeat integration check, not a new evaluation case.
Desktop and narrow layouts, curve tabs, window switching, file import errors,
the full evidence report and ZIP download were checked locally. No detector
features, weights, thresholds or evaluation results changed for the interface.
