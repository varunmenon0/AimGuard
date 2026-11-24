"""Loopback-only web interface; detector runs in its original Python environment."""

import argparse
import asyncio
import secrets
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from aimguard.local_store import Workspace


class LocalReplay(BaseModel):
    path: str = Field(min_length=1, max_length=4096)


class MatchAnalysis(BaseModel):
    replay_id: str = Field(min_length=1, max_length=64)


class Analysis(MatchAnalysis):
    steamid: str = Field(pattern=r"^\d{17}$")


def create_app(root=None, workspace=None, start_worker=True):
    root = Path(root or Path(__file__).resolve().parents[1])
    ws = workspace or Workspace(root)
    token = secrets.token_urlsafe(32)

    @asynccontextmanager
    async def lifespan(app):
        if start_worker:
            await asyncio.to_thread(ws.start)
        yield
        if start_worker:
            await asyncio.to_thread(ws.close)

    app = FastAPI(
        title="AimGuard Local",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.state.workspace = ws
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1"])

    @app.middleware("http")
    async def local_guard(request, call_next):
        origin = request.headers.get("origin")
        if origin and origin != f"{request.url.scheme}://{request.headers.get('host')}":
            return JSONResponse(
                {
                    "detail": "This interface accepts requests from its own local page only."
                },
                status_code=403,
            )
        if (
            request.url.path.startswith("/api/")
            and request.url.path
            not in (
                "/api/bootstrap",
                "/api/ping",
            )
            and not secrets.compare_digest(
                request.headers.get("x-aimguard-token", ""), token
            )
        ):
            return JSONResponse(
                {"detail": "Reload the local page to reconnect."}, status_code=403
            )
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Cache-Control"] = (
            "no-store" if request.url.path.startswith("/api/") else "no-cache"
        )
        response.headers["X-AimGuard-Local"] = "1"
        return response

    @app.exception_handler(KeyError)
    async def missing(request, error):
        return JSONResponse({"detail": str(error).strip("'")}, status_code=404)

    @app.exception_handler(ValueError)
    async def invalid(request, error):
        return JSONResponse({"detail": str(error)}, status_code=400)

    @app.exception_handler(OSError)
    async def file_error(request, error):
        return JSONResponse(
            {
                "detail": "This local file is unavailable. Check its location and permissions."
            },
            status_code=400,
        )

    @app.get("/api/ping")
    def ping():
        return {"app": "AimGuard", "workspace": str(root.resolve())}

    @app.get("/api/bootstrap")
    def bootstrap():
        return {
            "token": token,
            "model": ws.health,
            "storage": str(ws.directory),
            "workspace": str(root.resolve()),
            "max_file_bytes": 2 * 1024**3,
        }

    @app.get("/api/replays")
    def replays():
        with ws.lock:
            return sorted(
                ws.replays.values(), key=lambda r: r["modified_ns"], reverse=True
            )

    @app.post("/api/replays/refresh")
    async def refresh():
        await asyncio.to_thread(ws.discover)
        ws.save()
        return {"count": len(ws.replays)}

    @app.post("/api/replays/local")
    def local(body: LocalReplay):
        replay = ws.add_replay(body.path)
        ws.save()
        return replay

    @app.post("/api/replays/upload")
    async def upload(request: Request, name: str = "replay.dem"):
        if (
            Path(name).name != name
            or not name.lower().endswith(".dem")
            or len(name) > 240
        ):
            raise HTTPException(400, "Select a .dem replay file.")
        limit = 2 * 1024**3
        try:
            declared = int(request.headers.get("content-length", "0"))
        except ValueError:
            raise HTTPException(400, "Invalid file length.")
        if declared > limit:
            raise HTTPException(413, "Replay files must be 2 GiB or smaller.")
        directory = ws.directory / "inbox" / uuid.uuid4().hex
        directory.mkdir(parents=True)
        partial = directory / (name + ".partial")
        size = 0
        try:
            with partial.open("xb") as f:
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > limit:
                        raise HTTPException(
                            413, "Replay files must be 2 GiB or smaller."
                        )
                    await asyncio.to_thread(f.write, chunk)
            with partial.open("rb") as f:
                magic = f.read(8)
            if magic != b"PBDEMS2\x00":
                raise HTTPException(
                    400, "This file is not a CS2 replay. Choose a Source 2 .dem file."
                )
            final = directory / name
            partial.replace(final)
            replay = ws.add_replay(final)
            ws.save()
            return replay
        except BaseException:
            partial.unlink(missing_ok=True)
            raise

    @app.get("/api/replays/{identity}/players")
    def players(identity: str):
        ws.replay(identity)
        with ws.lock:
            if identity in ws.metadata:
                return dict(status="ready", **ws.metadata[identity])
        job = ws.enqueue(identity)
        return {"status": "pending", "job": job}

    @app.post("/api/analyses")
    def analyze(body: Analysis):
        return ws.enqueue(body.replay_id, body.steamid)

    @app.post("/api/matches")
    def analyze_match(body: MatchAnalysis):
        return ws.enqueue_match(body.replay_id)

    @app.get("/api/matches")
    def matches():
        with ws.lock:
            return sorted(
                [ws.match(identity) for identity in ws.matches],
                key=lambda m: m["created"],
                reverse=True,
            )

    @app.get("/api/matches/{identity}")
    def match(identity: str):
        return ws.match(identity)

    @app.post("/api/matches/{identity}/cancel")
    def cancel_match(identity: str):
        ws.cancel_match(identity)
        return ws.match(identity)

    @app.get("/api/jobs")
    def jobs():
        with ws.lock:
            return sorted(
                [ws.public_job(j) for j in ws.jobs.values() if j["kind"] == "analysis"],
                key=lambda j: j["created"],
                reverse=True,
            )

    @app.get("/api/jobs/{identity}")
    def job(identity: str):
        return ws.job(identity)

    @app.post("/api/jobs/{identity}/cancel")
    def cancel(identity: str):
        ws.cancel(identity)
        return ws.job(identity)

    @app.get("/api/jobs/{identity}/evidence")
    async def evidence(identity: str):
        return await asyncio.to_thread(ws.evidence, identity)

    @app.get("/api/jobs/{identity}/windows/{window_id}")
    async def curve(identity: str, window_id: int):
        return await asyncio.to_thread(ws.curve, identity, window_id)

    @app.get("/reports/{identity}/{relative:path}")
    def report(identity: str, relative: str):
        path = ws.artifact(identity, relative)
        response = FileResponse(path)
        if path.suffix == ".html":
            response.headers["Content-Security-Policy"] = (
                "sandbox allow-scripts; default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:"
            )
        return response

    @app.get("/exports/{identity}")
    async def export(identity: str):
        path = await asyncio.to_thread(ws.bundle, identity)
        return FileResponse(
            path,
            filename=f"AimGuard-{identity[:12]}-evidence.zip",
            media_type="application/zip",
        )

    dist = root / "ui/dist"
    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/")
    def index():
        if not (dist / "index.html").exists():
            raise HTTPException(
                503,
                "The interface bundle is missing. Build ui/ or restore the tracked ui/dist files.",
            )
        return FileResponse(dist / "index.html")

    return app


if __name__ == "__main__":
    import uvicorn

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--port", type=int, default=8765)
    a = p.parse_args()
    uvicorn.run(create_app(), host="127.0.0.1", port=a.port, log_level="warning")
