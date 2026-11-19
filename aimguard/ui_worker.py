"""Small JSON bridge executed only in the original detector environment."""

import argparse
import json
from pathlib import Path


def health(model):
    import platform

    from aimguard.baseline import digest
    from aimguard.offline_detector import load

    bundle = load(model)
    return {
        "ready": True,
        "version": bundle["feature_version"],
        "threshold": bundle["threshold"],
        "tickrate": bundle["tickrate"],
        "model_sha256": digest(Path(model) / "model.json"),
        "python": platform.python_version(),
    }


def inspect(demo):
    from demoparser2 import DemoParser

    from aimguard.gameplay import identity_strings

    parser = DemoParser(str(demo))
    header = parser.parse_header()
    info = parser.parse_player_info()
    ticks = parser.parse_ticks([])
    names = {}
    teams = {}
    counts = {}
    for frame in (info, ticks):
        frame = frame.copy()
        frame["steamid"] = identity_strings(frame["steamid"])
        for steamid, part in frame.groupby("steamid", sort=False):
            if not steamid.isdigit():
                continue
            n = int(steamid)
            if n >> 32 != 0x01100001 or not n & 0xFFFFFFFF:
                continue
            if "name" in part:
                values = part["name"].dropna()
                if len(values):
                    names[steamid] = str(values.iloc[-1])[:120]
            if "team_number" in part:
                values = part["team_number"].dropna()
                if len(values):
                    teams[steamid] = int(values.iloc[-1])
            if "tick" in part:
                counts[steamid] = len(part)
    players = [
        {
            "steamid": s,
            "name": names.get(s, s),
            "team": teams.get(s),
            "samples": counts.get(s, 0),
        }
        for s in sorted(set(names) | set(counts))
    ]
    if not players:
        raise ValueError("No supported player identities were found in this replay.")
    return {"map": header.get("map_name", "Unknown map"), "players": players}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=["health", "inspect"])
    p.add_argument("path", type=Path)
    p.add_argument("--output", type=Path)
    a = p.parse_args()
    result = health(a.path) if a.command == "health" else inspect(a.path)
    if a.output:
        a.output.parent.mkdir(parents=True, exist_ok=True)
        a.output.write_text(json.dumps(result, ensure_ascii=False))
    else:
        print(json.dumps(result, ensure_ascii=False))
