"""Whole-match admission, lifecycle and outcome accounting."""

from pathlib import Path

import pytest

from aimguard.local_store import Workspace


def workspace(tmp_path, count=10):
    ws = Workspace(tmp_path)
    ws.health = {"ready": True, "model_sha256": "fixed"}
    source = tmp_path / "match.dem"
    source.write_bytes(b"PBDEMS2\0demo")
    replay = ws.add_replay(source)
    ws.metadata[replay["id"]] = {
        "players": [
            {"steamid": str(76561199000000001 + i), "name": f"Player {i}"}
            for i in range(count)
        ]
    }
    return ws, replay["id"]


def test_ten_player_match_uses_one_queue_slot_and_deduplicates(tmp_path):
    ws, r = workspace(tmp_path)
    match = ws.enqueue_match(r)
    assert match["counts"]["total"] == 10 and match["counts"]["queued"] == 10
    assert len(ws.jobs) == 10 and ws.work.qsize() == 10
    assert ws.enqueue_match(r)["id"] == match["id"]
    assert len(ws.jobs) == 10
    assert all(j["match_id"] == match["id"] for j in ws.jobs.values())
    assert all("artifact" not in j for j in match["jobs"])


def test_match_admission_respects_queue_capacity_without_partial_batch(tmp_path):
    ws, r = workspace(tmp_path)
    for p in ws.metadata[r]["players"][:6]:
        ws.enqueue(r, p["steamid"])
    with pytest.raises(ValueError, match="queue is full"):
        ws.enqueue_match(r)
    assert len(ws.jobs) == 6 and not ws.matches and ws.work.qsize() == 6


def test_all_outcomes_are_counted_without_turning_errors_into_negatives(tmp_path):
    ws, r = workspace(tmp_path, 7)
    m = ws.enqueue_match(r)
    for j, status in zip(
        ws.jobs.values(),
        [
            "flag_for_review",
            "not_flagged",
            "insufficient_evidence",
            "failed",
            "cancelled",
            "interrupted",
            "not_flagged",
        ],
    ):
        if status in ("failed", "cancelled", "interrupted"):
            j["status"] = status
        else:
            j.update(
                status="completed",
                prediction={
                    "status": status,
                    "score": None if status == "insufficient_evidence" else 0.8,
                },
            )
    result = ws.match(m["id"])
    assert result["status"] == "partial"
    assert result["counts"] == {
        "total": 7,
        "completed": 4,
        "flagged": 1,
        "not_flagged": 2,
        "insufficient": 1,
        "failed": 1,
        "cancelled": 1,
        "interrupted": 1,
        "queued": 0,
        "running": 0,
    }


def test_cancel_only_affects_owned_jobs_and_preserves_completed_results(tmp_path):
    ws, r = workspace(tmp_path)
    solo = ws.enqueue(r, ws.metadata[r]["players"][0]["steamid"])
    m = ws.enqueue_match(r)
    first = ws.jobs[m["job_ids"][0]]
    first.update(status="completed", prediction={"status": "not_flagged", "score": 0.2})
    ws.cancel_match(m["id"])
    result = ws.match(m["id"])
    assert result["status"] == "cancelled" and result["counts"]["cancelled"] == 9
    assert result["counts"]["not_flagged"] == 1
    assert ws.job(solo["id"])["status"] == "queued"


def test_restart_retains_match_and_marks_unfinished_players_interrupted(tmp_path):
    ws, r = workspace(tmp_path)
    m = ws.enqueue_match(r)
    restored = Workspace(tmp_path).match(m["id"])
    assert restored["status"] == "partial" and restored["counts"]["interrupted"] == 10
    assert restored["counts"]["not_flagged"] == 0


def test_invalid_rosters_and_unavailable_engine_do_not_leave_partial_matches(tmp_path):
    ws, r = workspace(tmp_path)
    ws.metadata[r]["players"].append(ws.metadata[r]["players"][0])
    with pytest.raises(ValueError, match="duplicate"):
        ws.enqueue_match(r)
    assert not ws.matches and not ws.jobs
    ws.metadata[r]["players"].pop()
    ws.health["ready"] = False
    with pytest.raises(ValueError, match="unavailable"):
        ws.enqueue_match(r)
    assert not ws.matches and not ws.jobs


def test_fresh_review_after_terminal_match_does_not_reuse_old_scores(tmp_path):
    ws, r = workspace(tmp_path)
    old = ws.enqueue_match(r)
    ws.cancel_match(old["id"])
    new = ws.enqueue_match(r)
    assert set(old["job_ids"]).isdisjoint(new["job_ids"])
    assert new["counts"]["queued"] == 10


def test_changed_recording_fails_all_owned_jobs_without_scoring(tmp_path, monkeypatch):
    ws, r = workspace(tmp_path)
    match = ws.enqueue_match(r)
    path = Path(ws.replays[r]["path"])
    path.write_bytes(b"PBDEMS2\0different recording")
    ws.add_replay(path)  # Library refresh must not silently update queued inputs.

    def unexpected_process(*args, **kwargs):
        raise AssertionError("Scoring must not start for a replaced recording")

    monkeypatch.setattr("aimguard.local_store.subprocess.Popen", unexpected_process)
    ws.work.put(None)
    ws._worker()
    result = ws.match(match["id"])
    assert result["counts"]["failed"] == 10
    assert result["counts"]["not_flagged"] == 0
    assert all("replay changed" in j["detail"] for j in result["jobs"])


def test_admission_failure_does_not_execute_half_a_match(tmp_path, monkeypatch):
    ws, r = workspace(tmp_path)
    enqueue = ws.enqueue

    def fail_after_two(*args, **kwargs):
        if len(ws.jobs) == 2:
            raise OSError("Disk unavailable")
        return enqueue(*args, **kwargs)

    monkeypatch.setattr(ws, "enqueue", fail_after_two)
    with pytest.raises(OSError, match="Disk unavailable"):
        ws.enqueue_match(r)
    assert not ws.matches and not ws.jobs and ws.work.empty()
