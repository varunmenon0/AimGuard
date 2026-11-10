from demoparser2 import DemoParser

demo = "data/raw/your-end-vs-damajuana-m1-cache.dem"
parser = DemoParser(demo)

properties = [
    "pitch",
    "yaw",
    "health",
    "life_state",
    "team_num",
    "X",
    "Y",
    "Z",
]

print("\n=== PLAYER PROPERTIES ===")

for prop in properties:
    try:
        df = parser.parse_ticks([prop])
        print(f"{prop}: OK ({len(df)} rows)")
    except Exception as exc:
        print(f"{prop}: unavailable ({type(exc).__name__}: {exc})")

events = [
    "round_start",
    "round_freeze_end",
    "round_end",
    "player_death",
    "weapon_fire",
    "player_hurt",
]

print("\n=== GAME EVENTS ===")

for event in events:
    try:
        df = parser.parse_event(event)
        print(f"{event}: OK ({len(df)} events)")
        print(f"  Columns: {df.columns.tolist()}")
    except Exception as exc:
        print(f"{event}: unavailable ({type(exc).__name__}: {exc})")
