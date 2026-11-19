"""Install and verify the packaged application in a fresh clone."""

import os
import platform
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from aimguard.model_package import PUBLIC_MODEL, verify_package


def interpreter(directory):
    return directory / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def main():
    model = verify_package(ROOT / PUBLIC_MODEL, ROOT)
    required = model["python_version"]
    if platform.python_version() != required:
        raise SystemExit(
            f"Use Python {required} for this frozen model; found {platform.python_version()}. See docs/INSTALL.md. No environment was changed."
        )
    engine_dir = ROOT / ".venv"
    engine = interpreter(engine_dir)
    if not engine_dir.exists():
        print("Preparing the detector environment…", flush=True)
        venv.EnvBuilder(with_pip=True).create(engine_dir)
        subprocess.run(
            [
                str(engine),
                "-m",
                "pip",
                "install",
                "--only-binary=:all:",
                "-r",
                str(ROOT / "requirements-runtime.txt"),
            ],
            check=True,
        )
    if not engine.exists():
        raise SystemExit(
            "An incomplete .venv already exists. Use a fresh checkout or move that environment before retrying. Existing environments are not overwritten."
        )
    result = subprocess.run(
        [str(engine), "-m", "aimguard.ui_worker", "health", str(ROOT / PUBLIC_MODEL)],
        cwd=ROOT,
        capture_output=True,
        encoding="utf-8",
        env=dict(os.environ, PYTHONUTF8="1"),
        check=False,
    )
    if result.returncode:
        print(result.stderr or result.stdout, file=sys.stderr)
        raise SystemExit(
            "The detector environment does not match this package. See docs/INSTALL.md. Existing environments are not modified."
        )
    web_dir = ROOT / ".ui-venv"
    web = interpreter(web_dir)
    if not web_dir.exists():
        print("Preparing the separate interface environment…", flush=True)
        venv.EnvBuilder(with_pip=True).create(web_dir)
        subprocess.run(
            [str(web), "-m", "pip", "install", "-r", str(ROOT / "requirements-ui.txt")],
            check=True,
        )
    if (
        not web.exists()
        or subprocess.run(
            [str(web), "-c", "import fastapi,uvicorn"], capture_output=True, check=False
        ).returncode
    ):
        raise SystemExit(
            "The interface environment is incomplete. See docs/INSTALL.md. Existing environments are not overwritten."
        )
    if not (ROOT / "ui/dist/index.html").is_file():
        raise SystemExit("The packaged interface is missing. Restore ui/dist from Git.")
    print("\nAimGuard is installed. The bundled model and frozen runtime are verified.")
    print(
        "Add your own CS2 .dem file; a new installation starts with an empty library."
    )
    print(
        "Start: .venv\\Scripts\\python.exe scripts\\launch_ui.py"
        if os.name == "nt"
        else "Start: .venv/bin/python scripts/launch_ui.py"
    )


if __name__ == "__main__":
    main()
