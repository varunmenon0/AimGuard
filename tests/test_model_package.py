"""The public model is portable, parameter-identical and contains no research IDs."""

import json
from pathlib import Path

import pytest

from aimguard.model_package import (
    INFERENCE_FIELDS,
    PARAMETER_FIELDS,
    PUBLIC_MODEL,
    default_model,
    digest,
    export_inference,
    parameter_digest,
    verify_package,
)

ROOT = Path(__file__).resolve().parents[1]


def test_public_bundle_has_only_inference_fields_and_matching_source_receipts():
    bundle = verify_package(ROOT / PUBLIC_MODEL, ROOT)
    assert set(bundle) == set(INFERENCE_FIELDS)
    assert not {"training", "excluded_participants", "source_sha256", "groups"} & set(
        bundle
    )
    assert bundle["threshold"] == 0.75
    assert bundle["python_version"] == "3.12.10"
    assert len(bundle["code_sha256"]) == 16
    serialized = json.dumps(bundle)
    assert "/Users/" not in serialized and "7656119" not in serialized


def test_export_preserves_parameters_and_strips_research_metadata(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    bundle = json.loads((ROOT / PUBLIC_MODEL / "model.json").read_text())
    bundle.update(
        training=[{"steamid": "private identity"}],
        excluded_participants=["private identity"],
        source_sha256={"/private/path": "hash"},
    )
    (source / "model.json").write_text(json.dumps(bundle))
    (source / "model.sha256").write_text(digest(source / "model.json"))
    target = tmp_path / "public"
    receipt = export_inference(source, target)
    public = json.loads((target / "model.json").read_text())
    assert all(public[key] == bundle[key] for key in PARAMETER_FIELDS)
    assert receipt["parameters_sha256"] == parameter_digest(bundle)
    assert "private identity" not in json.dumps(public)
    assert receipt["source_model_sha256"] == digest(source / "model.json")
    with pytest.raises(FileExistsError):
        export_inference(source, target)


def test_package_rejects_tampering_and_never_rewrites_source(tmp_path):
    import shutil

    target = tmp_path / "public"
    shutil.copytree(ROOT / PUBLIC_MODEL, target)
    original = (target / "model.json").read_bytes()
    bundle = json.loads(original)
    bundle["intercept"] += 1
    (target / "model.json").write_text(json.dumps(bundle))
    with pytest.raises(ValueError, match="checksum"):
        verify_package(target, ROOT)
    with pytest.raises(ValueError, match="checksum"):
        export_inference(target, tmp_path / "new")
    assert not (tmp_path / "new").exists()


def test_new_clone_uses_public_model_and_local_research_model_stays_selected(tmp_path):
    assert default_model(tmp_path) == tmp_path / PUBLIC_MODEL
    research = tmp_path / "outputs/xguardian/offline-v06/frozen"
    research.mkdir(parents=True)
    (research / "model.json").write_text("{}")
    assert default_model(tmp_path) == research


def test_runtime_requirements_match_every_model_dependency():
    bundle = json.loads((ROOT / PUBLIC_MODEL / "model.json").read_text())
    pins = {
        line.split("==")[0]: line.split("==")[1]
        for line in (ROOT / "requirements-runtime.txt").read_text().splitlines()
        if "==" in line
    }
    assert all(
        pins[name] == version for name, version in bundle["dependencies"].items()
    )


def test_setup_refuses_wrong_python_before_creating_environments(tmp_path, monkeypatch):
    from scripts import setup_local

    monkeypatch.setattr(setup_local, "ROOT", tmp_path)
    monkeypatch.setattr(
        setup_local, "verify_package", lambda *args: {"python_version": "3.12.10"}
    )
    monkeypatch.setattr(setup_local.platform, "python_version", lambda: "3.12.11")
    with pytest.raises(SystemExit, match="No environment was changed"):
        setup_local.main()
    assert not (tmp_path / ".venv").exists()


def test_setup_does_not_install_over_existing_incompatible_environment(
    tmp_path, monkeypatch
):
    from types import SimpleNamespace

    from scripts import setup_local

    engine = setup_local.interpreter(tmp_path / ".venv")
    engine.parent.mkdir(parents=True)
    engine.write_text("existing")
    calls = []
    monkeypatch.setattr(setup_local, "ROOT", tmp_path)
    monkeypatch.setattr(
        setup_local,
        "verify_package",
        lambda *args: {"python_version": setup_local.platform.python_version()},
    )

    def run(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=1, stderr="incompatible runtime", stdout="")

    monkeypatch.setattr(setup_local.subprocess, "run", run)
    with pytest.raises(SystemExit, match="not modified"):
        setup_local.main()
    assert engine.read_text() == "existing"
    assert not any("pip" in args for args in calls)
    assert not (tmp_path / ".ui-venv").exists()
