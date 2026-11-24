"""Run in .ui-venv; the original detector environment needs no web dependencies."""

from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient

from aimguard.local_store import Workspace
from aimguard.local_web import create_app


@pytest.fixture
def client(tmp_path):
    ws = Workspace(tmp_path)
    ws.health = {"ready": True, "model_sha256": "frozen-model"}
    with TestClient(
        create_app(tmp_path, workspace=ws, start_worker=False),
        base_url="http://127.0.0.1",
    ) as c:
        yield c, ws


def connect(c):
    c.headers["X-AimGuard-Token"] = c.get("/api/bootstrap").json()["token"]


def test_local_session_required_and_host_and_origin_checked(client):
    c, _ = client
    assert c.get("/api/replays").status_code == 403
    connect(c)
    assert c.get("/api/replays").status_code == 200
    assert (
        c.get("/api/replays", headers={"Origin": "https://example.org"}).status_code
        == 403
    )
    assert (
        c.get("/api/bootstrap", headers={"Host": "attacker.example"}).status_code == 400
    )
    assert (
        c.get("/api/replays", headers={"Origin": "http://127.0.0.1"}).status_code == 200
    )


def test_import_validates_content_filename_and_limit(client):
    c, ws = client
    connect(c)
    assert (
        c.post("/api/replays/upload?name=test.dem", content=b"not a replay").status_code
        == 400
    )
    assert (
        c.post(
            "/api/replays/upload?name=../test.dem", content=b"PBDEMS2\0demo"
        ).status_code
        == 400
    )
    assert (
        c.post(
            "/api/replays/upload?name=test.dem",
            headers={"content-length": str(2**31 + 1)},
            content=b"",
        ).status_code
        == 413
    )
    assert not list(ws.directory.rglob("*.partial"))
    response = c.post("/api/replays/upload?name=test.dem", content=b"PBDEMS2\0demo")
    assert response.status_code == 200
    r = response.json()
    assert Path(r["path"]).is_relative_to(ws.directory / "inbox")
    assert c.get(f"/api/replays/{r['id']}/players").json()["status"] == "pending"


def test_bad_player_or_model_fails_without_fabricated_prediction(client):
    c, ws = client
    connect(c)
    source = ws.root / "test.dem"
    source.write_bytes(b"PBDEMS2\0demo")
    replay = c.post("/api/replays/local", json={"path": str(source)}).json()
    body = {"replay_id": replay["id"], "steamid": "76561199187894640"}
    assert c.post("/api/analyses", json=body).status_code == 400
    assert c.post("/api/analyses", json={**body, "steamid": "123"}).status_code == 422
    ws.health["ready"] = False
    assert c.get(f"/api/replays/{replay['id']}/players").status_code == 400
    assert c.get("/api/jobs").json() == []


def test_missing_reports_and_missing_bundle_are_explicit(client):
    c, _ = client
    connect(c)
    assert c.get("/api/jobs/unknown/evidence").status_code == 404
    assert c.get("/reports/unknown/prediction.json").status_code == 404
    assert c.get("/").status_code == 503


def test_match_api_admits_ten_players_and_supports_cancel(client):
    c, ws = client
    connect(c)
    source = ws.root / "match.dem"
    source.write_bytes(b"PBDEMS2\0demo")
    r = ws.add_replay(source)
    ws.metadata[r["id"]] = {
        "players": [
            {"steamid": str(76561199000000001 + i), "name": f"Player {i}"}
            for i in range(10)
        ]
    }
    response = c.post("/api/matches", json={"replay_id": r["id"]})
    assert response.status_code == 200
    match = response.json()
    assert match["counts"]["total"] == 10
    assert (
        c.post("/api/matches", json={"replay_id": r["id"]}).json()["id"] == match["id"]
    )
    assert len(c.get("/api/matches").json()) == 1
    assert c.get("/api/matches/" + match["id"]).json()["counts"]["queued"] == 10
    result = c.post("/api/matches/" + match["id"] + "/cancel").json()
    assert result["status"] == "cancelled" and result["counts"]["cancelled"] == 10
    assert c.get("/api/matches/missing").status_code == 404


def test_match_requires_session_and_inspected_roster(client):
    c, _ = client
    assert c.post("/api/matches", json={"replay_id": "missing"}).status_code == 403
    connect(c)
    assert c.post("/api/matches", json={"replay_id": "missing"}).status_code == 404
