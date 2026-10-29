import json
from pathlib import Path

path = Path("data/all_matches.json")
with path.open("r", encoding="utf-8") as f:
    matches = json.load(f)

print(f"Loaded {len(matches)} matches from {path}")