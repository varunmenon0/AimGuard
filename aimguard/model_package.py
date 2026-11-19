"""Publish an inference-only copy without changing the research model."""

import hashlib
import json
from pathlib import Path

INFERENCE_FIELDS = (
    "schema_version",
    "model_kind",
    "created_at_utc",
    "feature_version",
    "phase_policy",
    "threshold",
    "feature_names",
    "configuration",
    "hyperparameters",
    "tickrate",
    "scaler_mean",
    "scaler_scale",
    "coefficients",
    "intercept",
    "code_sha256",
    "dependencies",
    "python_version",
    "note",
)
PARAMETER_FIELDS = (
    "feature_names",
    "scaler_mean",
    "scaler_scale",
    "coefficients",
    "intercept",
)
PUBLIC_MODEL = Path("artifacts/aimguard-v0.6")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def parameter_digest(bundle):
    encoded = json.dumps(
        {k: bundle[k] for k in PARAMETER_FIELDS}, sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def export_inference(source, output):
    source, output = Path(source), Path(output)
    if digest(source / "model.json") != (source / "model.sha256").read_text().strip():
        raise ValueError("Source model checksum differs")
    original = json.loads((source / "model.json").read_text())
    bundle = {key: original[key] for key in INFERENCE_FIELDS}
    # No training rows, player identities, source paths or holdout reservations.
    output.mkdir(parents=True, exist_ok=False)
    (output / "model.json").write_text(
        json.dumps(bundle, indent=2) + "\n", encoding="utf-8"
    )
    checksum = digest(output / "model.json")
    (output / "model.sha256").write_text(checksum + "\n", encoding="utf-8")
    receipt = {
        "schema_version": 1,
        "purpose": "inference-only",
        "source_model_sha256": digest(source / "model.json"),
        "model_sha256": checksum,
        "parameters_sha256": parameter_digest(bundle),
        "python_version": bundle["python_version"],
        "license": "MIT",
        "note": "Weights, preprocessing, threshold and runtime receipts match the research artifact. Research identities and evaluation reservations are omitted. Use for scoring, not fresh evaluation.",
    }
    (output / "PACKAGE.json").write_text(
        json.dumps(receipt, indent=2) + "\n", encoding="utf-8"
    )
    return receipt


def verify_package(directory, root):
    directory, root = Path(directory), Path(root)
    bundle = json.loads((directory / "model.json").read_text())
    receipt = json.loads((directory / "PACKAGE.json").read_text())
    checksum = digest(directory / "model.json")
    if (
        checksum != (directory / "model.sha256").read_text().strip()
        or checksum != receipt["model_sha256"]
    ):
        raise ValueError("Packaged model checksum differs")
    if set(bundle) != set(INFERENCE_FIELDS) or receipt["purpose"] != "inference-only":
        raise ValueError("Unexpected inference package contents")
    if parameter_digest(bundle) != receipt["parameters_sha256"]:
        raise ValueError("Packaged model parameters differ")
    for name, expected in bundle["code_sha256"].items():
        if Path(name).name != name or digest(root / "aimguard" / name) != expected:
            raise ValueError("Frozen source changed: " + name)
    return bundle


def default_model(root):
    root = Path(root)
    research = root / "outputs/xguardian/offline-v06/frozen"
    return research if (research / "model.json").exists() else root / PUBLIC_MODEL
