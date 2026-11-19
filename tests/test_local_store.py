"""Boundary tests for the local interface without web or numerical dependencies."""

import csv
import json
import sys
import zipfile
from pathlib import Path

import pytest

from aimguard.local_store import Workspace, atomic

STEAMID = "76561199187894640"


@pytest.fixture
def workspace(tmp_path):
    ws = Workspace(tmp_path)
    ws.health = {"ready": True, "model_sha256": "frozen-model"}
    return ws


def replay(ws):
    path = ws.root / "match.dem"
    path.write_bytes(b"PBDEMS2\0demo")
    item = ws.add_replay(path)
    ws.metadata[item["id"]] = {
        "map": "de_dust2",
        "players": [{"steamid": STEAMID, "name": "Player", "team": 2}],
    }
    return item


@pytest.fixture
def completed(workspace):
    ws = workspace
    r = replay(ws)
    job = ws.enqueue(r["id"], STEAMID)
    private = ws.jobs[job["id"]]
    directory = Path(private["artifact"])
    directory.mkdir()
    prediction = {
        "model_sha256": "frozen-model",
        "status": "not_flagged",
        "score": 0.3,
        "steamid": STEAMID,
    }
    window = {
        "engagement_id": 0,
        "segment_id": 2,
        "round_id": 1,
        "weapon": "ak47",
        "shot_count": 1,
        "shot_ticks": [101],
        "duration_seconds": 2 / 64,
        "damage_dealt_events": 0,
        "start_tick": 100,
        "end_tick": 102,
    }
    atomic(directory / "prediction.json", prediction)
    atomic(
        directory / "analysis/report.json",
        {
            "source": r["path"],
            "steamid": STEAMID,
            "assumed_tickrate_hz": 64,
            "engagements": [window],
        },
    )
    atomic(
        directory / "tracking.json",
        {
            "windows": [
                {"engagement_id": 0, "nearest_before_first_shot": None, "tracks": []}
            ]
        },
    )
    with (directory / "analysis/telemetry.csv").open("w", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["tick", "segment_id", "yaw", "pitch", "name"]
        )
        writer.writeheader()
        writer.writerows(
            [
                {
                    "tick": 100,
                    "segment_id": 1,
                    "yaw": 0,
                    "pitch": 0,
                    "name": "Wrong life",
                },
                {
                    "tick": 100,
                    "segment_id": 2,
                    "yaw": 179,
                    "pitch": 0,
                    "name": "Player",
                },
                {
                    "tick": 101,
                    "segment_id": 2,
                    "yaw": -179,
                    "pitch": 0,
                    "name": "Player",
                },
                {
                    "tick": 102,
                    "segment_id": 2,
                    "yaw": -178,
                    "pitch": 0,
                    "name": "Player",
                },
            ]
        )
    (directory / "result.html").write_text("<h1>Result</h1>")
    private.update(status="completed", prediction=prediction)
    return ws, job["id"]


def test_venv_interpreter_symlink_is_preserved(tmp_path):
    engine = tmp_path / ".venv/bin/python"
    engine.parent.mkdir(parents=True)
    engine.symlink_to(sys.executable)
    assert Workspace(tmp_path).engine == engine
    assert Workspace(tmp_path).engine != engine.resolve()


def test_changed_replay_invalidates_inspected_roster(workspace):
    r = replay(workspace)
    Path(r["path"]).write_bytes(b"PBDEMS2\0changed recording")
    with pytest.raises(ValueError, match="file changed"):
        workspace.replay(r["id"])
    assert r["id"] not in workspace.metadata
    with pytest.raises(ValueError, match="inspected replay"):
        workspace.enqueue(r["id"], STEAMID)


def test_exact_player_identity_required_and_queue_is_deduplicated(workspace):
    r = replay(workspace)
    with pytest.raises(ValueError, match="inspected replay"):
        workspace.enqueue(r["id"], "76561199187894641")
    job = workspace.enqueue(r["id"], STEAMID)
    assert job["steamid"] == STEAMID
    assert workspace.enqueue(r["id"], STEAMID)["id"] == job["id"]
    assert workspace.work.qsize() == 1
    assert "artifact" not in job and "log" not in job


def test_unavailable_engine_cannot_produce_a_negative(workspace):
    r = replay(workspace)
    workspace.health["ready"] = False
    with pytest.raises(ValueError, match="unavailable"):
        workspace.enqueue(r["id"], STEAMID)
    assert not workspace.jobs


def test_queued_cancel_and_restart_are_explicit(workspace):
    r = replay(workspace)
    job = workspace.enqueue(r["id"], STEAMID)
    workspace.cancel(job["id"])
    assert workspace.job(job["id"])["status"] == "cancelled"
    second = workspace.enqueue(r["id"], STEAMID)
    reloaded = Workspace(workspace.root)
    assert reloaded.job(second["id"])["status"] == "interrupted"
    assert "prediction" not in reloaded.job(second["id"])


def test_artifact_traversal_and_symlink_escape_are_rejected(completed):
    ws, identity = completed
    outside = ws.root / "private.txt"
    outside.write_text("private")
    root = ws.artifact(identity, "prediction.json").parent
    (root / "escape.txt").symlink_to(outside)
    for relative in ("../../../../private.txt", str(outside), "escape.txt"):
        with pytest.raises(KeyError):
            ws.artifact(identity, relative)
    ws.jobs[identity]["status"] = "failed"
    with pytest.raises(KeyError):
        ws.evidence(identity)


def test_curve_respects_player_life_and_wraps_angles(completed):
    ws, identity = completed
    curve = ws.curve(identity, 0)
    assert len(curve["points"]) == 3
    assert [p["yaw"] for p in curve["points"]] == [179, 181, 182]
    assert curve["points"][1]["speed"] == 128
    assert curve["shots"] == [0]
    assert curve["tracking"] == []
    with pytest.raises(KeyError):
        ws.curve(identity, 999)


def test_export_contains_portable_evidence_and_no_replays(completed):
    ws, identity = completed
    with zipfile.ZipFile(ws.bundle(identity)) as z:
        assert "prediction.json" in z.namelist()
        assert "result.html" in z.namelist()
        assert not any(n.endswith(".dem") or n.startswith("/") for n in z.namelist())
        assert json.loads(z.read("prediction.json"))["steamid"] == STEAMID


def test_opponent_curve_marks_gaps_instead_of_joining_segments(completed):
    ws, identity = completed
    path = ws.artifact(identity, "tracking.json")
    atomic(
        path,
        {
            "windows": [
                {
                    "engagement_id": 0,
                    "nearest_before_first_shot": "opponent",
                    "tracks": [
                        {
                            "opponent_id": "opponent",
                            "ticks": [100, 101, 110],
                            "segment_ids": [0, 0, 1],
                            "signed_error_degrees": [1, 2, 3],
                            "yaw_rate_dps": [None, 64, None],
                            "bearing_rate_dps": [None, 0, None],
                        }
                    ],
                }
            ]
        },
    )
    curve = ws.curve(identity, 0)
    assert [p["break_before"] for p in curve["tracking"]] == [False, False, True]


def test_discovery_does_not_follow_symlinks_outside_library(workspace):
    external = workspace.root / "outside.dem"
    external.write_bytes(b"PBDEMS2\0demo")
    data = workspace.root / "data"
    data.mkdir()
    (data / "escape.dem").symlink_to(external)
    workspace.discover()
    assert not workspace.replays
