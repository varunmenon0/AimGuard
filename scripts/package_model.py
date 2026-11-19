"""Export the checked research artifact as a public inference-only package."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from aimguard.model_package import export_inference
from aimguard.offline_detector import load


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    load(args.source)
    receipt = export_inference(args.source, args.output)
    load(args.output)
    print("Verified inference package: " + receipt["model_sha256"])


if __name__ == "__main__":
    main()
