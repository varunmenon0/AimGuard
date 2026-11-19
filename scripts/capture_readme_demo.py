"""Capture four real local-interface screens from existing completed reports.

Run in .ui-venv after installing Playwright and its Chromium browser. Reports
remain local; only PNGs are published. Display names are pseudonymized, and
Steam identities are visibly hidden in the screenshots. Scores/curves are intact.
"""

import argparse
import copy
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import uvicorn
from playwright.sync_api import sync_playwright

from aimguard.local_store import Workspace
from aimguard.local_web import create_app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--passed", type=Path, required=True)
    parser.add_argument("--flagged", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "docs/images")
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()
    ws = Workspace(ROOT, state_dir=ROOT / "outputs/readme-demo")
    ws.jobs = {}
    ws.replays = {}
    ws.metadata = {}
    health = subprocess.run(
        [str(ws.engine), "-m", "aimguard.ui_worker", "health", str(ws.model)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    ws.health = json.loads(health.stdout)
    ws.import_history()
    wanted = [args.passed.resolve(), args.flagged.resolve()]
    examples = [
        next(j for j in ws.jobs.values() if Path(j["artifact"]).resolve() == path)
        for path in wanted
    ]
    if [j["prediction"]["status"] for j in examples] != [
        "not_flagged",
        "flag_for_review",
    ]:
        raise ValueError(
            "Use one completed non-flag and one completed flag. Source labels must be checked separately."
        )
    # Keep a small curated workspace, rather than publishing a full research log.
    seen = {j["steamid"] for j in examples}
    extras = []
    for job in sorted(ws.jobs.values(), key=lambda j: j["created"], reverse=True):
        if job["steamid"] not in seen:
            extras.append(job)
            seen.add(job["steamid"])
        if len(extras) == 4:
            break
    jobs = [*examples, *extras]
    ws.jobs = {j["id"]: j for j in jobs}
    ws.replays = {j["replay_id"]: ws.replays[j["replay_id"]] for j in jobs}
    aliases = {j["steamid"]: f"Player {i:02}" for i, j in enumerate(jobs, 1)}
    for i, replay in enumerate(ws.replays.values(), 1):
        replay["name"] = f"match-{i:02}-{replay['map'].lower().replace(' ', '-')}.dem"
        replay["folder"] = "Local replays"
    for job in jobs:
        job["player"] = aliases[job["steamid"]]
        job["replay_name"] = ws.replays[job["replay_id"]]["name"]
    first = examples[0]
    replay = ws.replays[first["replay_id"]]
    inspected = subprocess.run(
        [str(ws.engine), "-m", "aimguard.ui_worker", "inspect", replay["path"]],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    roster = copy.deepcopy(json.loads(inspected.stdout))
    for player in roster["players"]:
        if player["steamid"] not in aliases:
            aliases[player["steamid"]] = f"Player {len(aliases) + 1:02}"
        player["name"] = aliases[player["steamid"]]
    ws.metadata[replay["id"]] = roster
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(ROOT, workspace=ws, start_worker=False),
            host="127.0.0.1",
            port=args.port,
            log_level="error",
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    if not server.started:
        raise RuntimeError("Demo server could not start")
    args.output.mkdir(parents=True, exist_ok=True)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(
                viewport={"width": 1440, "height": 1080}, device_scale_factor=1
            )
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(f"http://127.0.0.1:{args.port}")
            page.get_by_role("heading", name="Replay analysis.").wait_for()
            # Screenshot-only redaction; backend identities and controls stay intact.
            page.add_style_tag(
                content='.player-copy small,.player-heading p.mono{font-size:0!important}.player-copy small::after,.player-heading p.mono::after{content:"Identity hidden for public demo";font-size:9px}'
            )
            page.locator(f'button.replay-row[title="{replay["path"]}"]').click()
            page.locator(".player-row").first.wait_for()
            page.locator(".player-row").filter(has_text="Player 01").click()
            page.mouse.move(1100, 80)
            page.screenshot(path=str(args.output / "01-workspace.png"), full_page=True)
            page.get_by_role("button", name="Analysis history", exact=True).click()
            page.get_by_role("heading", name="Analysis history.").wait_for()
            page.screenshot(path=str(args.output / "02-history.png"), full_page=True)
            for job, filename in [
                (first, "03-legitimate-review.png"),
                (examples[1], "04-cheating-review.png"),
            ]:
                page.locator(".job-row").filter(has_text=job["player"]).click()
                page.get_by_role("img", name="Recorded angles trajectory").wait_for()
                page.screenshot(path=str(args.output / filename), full_page=True)
                page.get_by_role("button", name="Analysis history", exact=True).click()
            browser.close()
            if errors:
                raise RuntimeError(errors)
    finally:
        server.should_exit = True
        thread.join(timeout=5)
    print(
        "Captured four real interface screens; display identities redacted, measurements unchanged."
    )


if __name__ == "__main__":
    main()
