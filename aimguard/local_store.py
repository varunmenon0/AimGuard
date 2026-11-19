"""Local interface state, isolated detector subprocesses, and evidence adapters.

This module deliberately has no numerical or detector-library imports.
"""

import csv
import hashlib
import json
import math
import os
import queue
import subprocess
import threading
import uuid
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from aimguard.model_package import default_model


def stamp():
    return datetime.now(UTC).isoformat()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def human_map(value):
    return {
        "de_dust2": "Dust II",
        "de_mirage": "Mirage",
        "de_inferno": "Inferno",
        "de_ancient": "Ancient",
        "de_nuke": "Nuke",
        "de_anubis": "Anubis",
        "de_overpass": "Overpass",
        "de_cache": "Cache",
        "de_vertigo": "Vertigo",
    }.get(value, value.removeprefix("de_").replace("_", " ").title())


class Workspace:
    def __init__(self, root, engine=None, model=None, state_dir=None):
        self.root = Path(root).resolve()
        self.directory = Path(state_dir or self.root / "outputs/local-ui").resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        # Preserve the venv path: resolving its symlink would select base Python.
        self.engine = Path(
            engine
            or self.root
            / (".venv/Scripts/python.exe" if os.name == "nt" else ".venv/bin/python")
        ).absolute()
        self.model = Path(model or default_model(self.root)).resolve()
        self.lock = threading.RLock()
        self.work = queue.Queue()
        self.stopping = False
        self.process = None
        self.thread = None
        self.health = {"ready": False, "error": "Checking the analysis engine…"}
        self.replays = {}
        self.jobs = {}
        self.metadata = {}
        self.state_path = self.directory / "workspace.json"
        if self.state_path.exists():
            state = read(self.state_path)
            self.replays = state.get("replays", {})
            self.jobs = state.get("jobs", {})
            self.metadata = state.get("metadata", {})
        for job in self.jobs.values():
            if job["status"] in ("queued", "running"):
                job.update(
                    status="interrupted",
                    message="The local app stopped before this analysis finished.",
                    finished=stamp(),
                )

    def save(self):
        with self.lock:
            atomic(
                self.state_path,
                {"replays": self.replays, "jobs": self.jobs, "metadata": self.metadata},
            )

    def start(self):
        try:
            p = subprocess.run(
                [
                    str(self.engine),
                    "-m",
                    "aimguard.ui_worker",
                    "health",
                    str(self.model),
                ],
                cwd=self.root,
                capture_output=True,
                encoding="utf-8",
                env=dict(os.environ, PYTHONUTF8="1"),
                timeout=45,
                check=False,
            )
            if p.returncode:
                raise ValueError((p.stderr or p.stdout).strip()[-1600:])
            self.health = json.loads(p.stdout)
        except (OSError, ValueError, subprocess.TimeoutExpired) as e:
            self.health = {"ready": False, "error": str(e)}
        self.discover()
        self.import_history()
        self.save()
        self.thread = threading.Thread(
            target=self._worker, daemon=True, name="aimguard-local-worker"
        )
        self.thread.start()

    def close(self):
        self.stopping = True
        with self.lock:
            process = self.process
            if process and process.poll() is None:
                process.terminate()
        if process:
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
        self.work.put(None)
        if self.thread:
            self.thread.join(timeout=5)
        with self.lock:
            for job in self.jobs.values():
                if job["status"] in ("queued", "running"):
                    job.update(
                        status="interrupted",
                        message="The local app was closed.",
                        finished=stamp(),
                    )
            self.save()

    def add_replay(self, path):
        path = Path(path).expanduser().resolve()
        if not path.is_file() or path.suffix.lower() != ".dem":
            raise ValueError("Choose an existing .dem file.")
        stat = path.stat()
        if stat.st_size > 2 * 1024**3:
            raise ValueError("This interface supports replay files up to 2 GiB.")
        identity = hashlib.sha256(str(path).encode()).hexdigest()[:24]
        inferred = next(
            (
                m
                for m in [
                    "de_dust2",
                    "de_mirage",
                    "de_inferno",
                    "de_ancient",
                    "de_nuke",
                    "de_anubis",
                    "de_overpass",
                    "de_cache",
                    "de_vertigo",
                ]
                if m in path.stem
            ),
            "",
        )
        with self.lock:
            previous = self.replays.get(identity)
            if previous and (
                previous["size"] != stat.st_size
                or previous["modified_ns"] != stat.st_mtime_ns
            ):
                self.metadata.pop(identity, None)
            self.replays[identity] = {
                "id": identity,
                "path": str(path),
                "name": path.name,
                "size": stat.st_size,
                "modified_ns": stat.st_mtime_ns,
                "added": previous["added"] if previous else stamp(),
                "map": previous.get("map", human_map(inferred))
                if previous
                else human_map(inferred),
                "folder": path.parent.name,
            }
        return self.replays[identity]

    def discover(self):
        data = self.root / "data"
        if not data.exists():
            return
        for path in data.rglob("*.dem"):
            if len(self.replays) >= 2000:
                break
            try:
                if path.resolve().is_relative_to(data.resolve()):
                    self.add_replay(path)
            except (OSError, ValueError):
                continue

    def _name(self, artifact, steamid):
        try:
            with (artifact / "analysis/telemetry.csv").open(encoding="utf-8") as f:
                row = next(csv.DictReader(f))
                return row.get("name") or steamid
        except (OSError, StopIteration):
            return steamid

    def import_history(self):
        outputs = self.root / "outputs"
        for path in outputs.rglob("prediction.json"):
            if path.resolve().is_relative_to(self.directory):
                continue
            try:
                artifact = path.parent
                prediction = read(path)
                report = read(artifact / "analysis/report.json")
                if prediction.get("model_sha256") != self.health.get("model_sha256"):
                    continue
                identity = (
                    "saved-"
                    + hashlib.sha256(str(path.resolve()).encode()).hexdigest()[:20]
                )
                if identity in self.jobs:
                    continue
                demo = Path(report["source"])
                replay = self.add_replay(demo) if demo.exists() else None
                name = self._name(artifact, report["steamid"])
                self.jobs[identity] = {
                    "id": identity,
                    "kind": "analysis",
                    "status": "completed",
                    "origin": "saved",
                    "created": datetime.fromtimestamp(
                        path.stat().st_mtime, UTC
                    ).isoformat(),
                    "finished": datetime.fromtimestamp(
                        path.stat().st_mtime, UTC
                    ).isoformat(),
                    "replay_id": replay["id"] if replay else None,
                    "replay_name": demo.name,
                    "player": name,
                    "steamid": report["steamid"],
                    "map": replay["map"] if replay else "Unknown",
                    "artifact": str(artifact.resolve()),
                    "prediction": prediction,
                    "message": "Saved analysis",
                    "model_sha256": prediction["model_sha256"],
                }
                if replay:
                    self.jobs[identity]["map"] = replay["map"]
            except (OSError, ValueError, KeyError, TypeError):
                continue

    def replay(self, identity):
        replay = self.replays.get(identity)
        if not replay:
            raise KeyError("Replay not found.")
        path = Path(replay["path"])
        stat = path.stat()
        if stat.st_size != replay["size"] or stat.st_mtime_ns != replay["modified_ns"]:
            self.add_replay(path)
            raise ValueError(
                "This file changed. Select it again to refresh its player list."
            )
        return replay

    def public_job(self, job):
        result = {
            k: v
            for k, v in job.items()
            if k not in ("artifact", "log", "cancel_requested")
        }
        if job["status"] == "running":
            artifact = Path(job["artifact"])
            stage = 0
            if (artifact / "analysis/telemetry.csv").exists():
                stage = 1
            if (artifact / "analysis/report.json").exists():
                stage = 2
            if (artifact / "tracking.json").exists():
                stage = 3
            result["stage"] = stage
            result["message"] = (
                (
                    "Reading replay telemetry",
                    "Building combat windows",
                    "Matching opponent trajectories",
                    "Calculating review score",
                )[stage]
                if job["kind"] == "analysis"
                else "Reading players and match details"
            )
        return result

    def enqueue(self, replay_id, steamid=None):
        if not self.health["ready"]:
            raise ValueError(
                "The frozen analysis engine is unavailable. Open Settings for details."
            )
        replay = self.replay(replay_id)
        kind = "analysis" if steamid else "inspect"
        with self.lock:
            for job in self.jobs.values():
                if (
                    job["status"] in ("queued", "running")
                    and job["kind"] == kind
                    and job["replay_id"] == replay_id
                    and job.get("steamid") == steamid
                ):
                    return self.public_job(job)
            if (
                sum(j["status"] in ("queued", "running") for j in self.jobs.values())
                >= 6
            ):
                raise ValueError(
                    "The analysis queue is full. Let a current job finish first."
                )
            player = None
            if steamid:
                meta = self.metadata.get(replay_id)
                player = next(
                    (
                        p
                        for p in (meta or {}).get("players", [])
                        if p["steamid"] == steamid
                    ),
                    None,
                )
                if not player:
                    raise ValueError("Select a player from the inspected replay.")
            identity = uuid.uuid4().hex
            directory = self.directory / "runs" / identity
            directory.mkdir(parents=True, exist_ok=False)
            job = {
                "id": identity,
                "kind": kind,
                "status": "queued",
                "origin": "local",
                "created": stamp(),
                "replay_id": replay_id,
                "replay_name": replay["name"],
                "player": player["name"] if player else None,
                "steamid": steamid,
                "map": replay["map"],
                "artifact": str(directory / "scoring"),
                "log": str(directory / "worker.log"),
                "message": "Waiting for the local analysis engine",
            }
            self.jobs[identity] = job
            self.save()
            self.work.put(identity)
            return self.public_job(job)

    def cancel(self, identity):
        with self.lock:
            job = self.jobs[identity]
            if job["status"] not in ("queued", "running"):
                return
            job["cancel_requested"] = True
            if (
                job["status"] == "running"
                and self.process
                and self.process.poll() is None
            ):
                self.process.terminate()
            else:
                job.update(status="cancelled", finished=stamp(), message="Cancelled")
            self.save()

    def _worker(self):
        while not self.stopping:
            identity = self.work.get()
            if identity is None:
                return
            with self.lock:
                job = self.jobs[identity]
                if job["status"] != "queued":
                    continue
                job.update(status="running", started=stamp())
                self.save()
            try:
                replay = self.replay(job["replay_id"])
                directory = Path(job["log"]).parent
                if job["kind"] == "inspect":
                    target = directory / "inspection.json"
                    args = [
                        str(self.engine),
                        "-m",
                        "aimguard.ui_worker",
                        "inspect",
                        replay["path"],
                        "--output",
                        str(target),
                    ]
                else:
                    args = [
                        str(self.engine),
                        "-m",
                        "aimguard.offline_detector",
                        "score",
                        str(self.model),
                        replay["path"],
                        "--steamid",
                        job["steamid"],
                        "--output",
                        job["artifact"],
                    ]
                env = dict(
                    os.environ,
                    PYTHONUTF8="1",
                    MPLCONFIGDIR=str(self.directory / "matplotlib"),
                )
                with Path(job["log"]).open("w", encoding="utf-8") as log:
                    with self.lock:
                        if job.get("cancel_requested"):
                            raise InterruptedError("Cancelled")
                        self.process = subprocess.Popen(
                            args,
                            cwd=self.root,
                            stdout=log,
                            stderr=subprocess.STDOUT,
                            env=env,
                        )
                    code = self.process.wait()
                with self.lock:
                    if job.get("cancel_requested") or self.stopping:
                        raise InterruptedError("Cancelled")
                    if code:
                        detail = Path(job["log"]).read_text(
                            encoding="utf-8", errors="replace"
                        )[-2400:]
                        raise ValueError(
                            detail or "The detector stopped without producing a result."
                        )
                    if job["kind"] == "inspect":
                        meta = read(target)
                        self.metadata[job["replay_id"]] = meta
                        self.replays[job["replay_id"]]["map"] = human_map(meta["map"])
                        job["map"] = human_map(meta["map"])
                    else:
                        prediction = read(Path(job["artifact"]) / "prediction.json")
                        if prediction["model_sha256"] != self.health["model_sha256"]:
                            raise ValueError(
                                "The result does not match the selected frozen model."
                            )
                        job["prediction"] = prediction
                        job["model_sha256"] = prediction["model_sha256"]
                    job.update(
                        status="completed",
                        finished=stamp(),
                        message="Analysis complete"
                        if job["kind"] == "analysis"
                        else "Replay ready",
                    )
            except InterruptedError:
                job.update(status="cancelled", finished=stamp(), message="Cancelled")
            except Exception as e:  # noqa: BLE001 -- isolate each job; keep the queue alive
                job.update(
                    status="failed",
                    finished=stamp(),
                    message="Replay inspection failed"
                    if job["kind"] == "inspect"
                    else "Analysis could not be completed",
                    detail=str(e)[-2400:],
                )
            finally:
                with self.lock:
                    self.process = None
                    self.save()

    def job(self, identity):
        with self.lock:
            if identity not in self.jobs:
                raise KeyError("Analysis not found.")
            return self.public_job(self.jobs[identity])

    def artifact(self, identity, relative):
        job = self.jobs.get(identity)
        if not job or job["status"] != "completed" or job["kind"] != "analysis":
            raise KeyError("This analysis has no completed report.")
        root = Path(job["artifact"]).resolve()
        path = (root / relative).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise KeyError("Report file not found.")
        return path

    def evidence(self, identity):
        report = read(self.artifact(identity, "analysis/report.json"))
        prediction = read(self.artifact(identity, "prediction.json"))
        return {
            "prediction": prediction,
            "windows": [
                {
                    "id": w["engagement_id"],
                    "round": w["round_id"],
                    "weapon": w["weapon"],
                    "shots": w["shot_count"],
                    "duration": w["duration_seconds"],
                    "damage": w["damage_dealt_events"],
                    "start_tick": w["start_tick"],
                    "end_tick": w["end_tick"],
                }
                for w in report["engagements"]
            ],
            "tickrate": report["assumed_tickrate_hz"],
        }

    def curve(self, identity, window_id):
        report = read(self.artifact(identity, "analysis/report.json"))
        window = next(
            (w for w in report["engagements"] if w["engagement_id"] == window_id), None
        )
        if window is None:
            raise KeyError("Combat window not found.")
        tracking = read(self.artifact(identity, "tracking.json"))
        track_window = next(
            w for w in tracking["windows"] if w["engagement_id"] == window_id
        )
        candidate = next(
            (
                t
                for t in track_window["tracks"]
                if t["opponent_id"] == track_window["nearest_before_first_shot"]
            ),
            None,
        )
        rate = report["assumed_tickrate_hz"]
        first = window["shot_ticks"][0]
        points = []
        previous = None
        unwrapped = None
        with self.artifact(identity, "analysis/telemetry.csv").open(
            encoding="utf-8"
        ) as f:
            for row in csv.DictReader(f):
                tick = int(row["tick"])
                if row.get("segment_id") != str(window["segment_id"]):
                    continue
                if tick < window["start_tick"]:
                    continue
                if tick > window["end_tick"]:
                    break
                yaw = float(row["yaw"])
                pitch = float(row["pitch"])
                speed = None
                discontinuous = False
                if previous:
                    dt = (tick - previous[0]) / rate
                    dy = (yaw - previous[1] + 180) % 360 - 180
                    if 0 < dt <= 0.25:
                        speed = math.hypot(dy, pitch - previous[2]) / dt
                        unwrapped += dy
                    else:
                        unwrapped = yaw
                        discontinuous = True
                else:
                    unwrapped = yaw
                points.append(
                    {
                        "t": (tick - first) / rate,
                        "yaw": unwrapped,
                        "pitch": pitch,
                        "speed": speed,
                        "break_before": discontinuous,
                    }
                )
                previous = (tick, yaw, pitch)
        relative = []
        if candidate:
            relative = [
                {
                    "t": (tick - first) / rate,
                    "error": error,
                    "yaw_rate": yaw_rate,
                    "bearing_rate": bearing_rate,
                }
                for tick, error, yaw_rate, bearing_rate in zip(
                    candidate["ticks"],
                    candidate["signed_error_degrees"],
                    candidate["yaw_rate_dps"],
                    candidate["bearing_rate_dps"],
                )
            ]
            segments = candidate["segment_ids"]
            ticks = candidate["ticks"]
            for i, point in enumerate(relative):
                point["break_before"] = bool(
                    i
                    and (segments[i] != segments[i - 1] or ticks[i] - ticks[i - 1] > 1)
                )
        return {
            "window": window,
            "points": points,
            "tracking": relative,
            "shots": [(t - first) / rate for t in window["shot_ticks"]],
            "note": "Geometric opponent measurements do not establish visibility or intended target.",
        }

    def bundle(self, identity):
        self.artifact(identity, "prediction.json")
        self.jobs[identity]
        target = self.directory / "exports" / f"{identity}.zip"
        target.parent.mkdir(exist_ok=True)
        with self.lock:
            if not target.exists():
                temp = target.with_suffix(".partial")
                with zipfile.ZipFile(temp, "w", zipfile.ZIP_DEFLATED) as z:
                    for name in (
                        "result.html",
                        "prediction.json",
                        "tracking.json",
                        "analysis/review.html",
                        "analysis/report.json",
                        "analysis/events.json",
                    ):
                        try:
                            z.write(self.artifact(identity, name), name)
                        except KeyError:
                            continue
                temp.replace(target)
        return target
