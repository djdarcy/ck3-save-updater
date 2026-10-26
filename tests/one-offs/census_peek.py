"""Census step 2: what do the small keyed/positional blocks hold? Prints the head of each, per save.

Usage: python -I tests/one-offs/census_peek.py <save.ck3> [<save.ck3> ...]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from census_survey import load  # noqa: E402
from ck3_save_migrator import gamestate as gs  # noqa: E402

PATHS = ["dynasties/static_dynasties", "dynasties/static_dynasty_houses", "culture_manager/template_cultures",
         "coat_of_arms/coat_of_arms_manager_name_map", "county_manager/monthly_change",
         "county_manager/monthly_increase", "landed_titles/important_locations", "faiths/saints",
         "struggle_manager/database", "council_task_manager/queue", "variables/data", "stories/active",
         "faction_manager/factions", "important_action_manager/active"]


def main():
    for p in sys.argv[1:]:
        g = load(p)
        print(f"\n######## {Path(p).name}")
        for path in PATHS:
            try:
                b = gs.locate(g, path)
            except gs.GamestateError:
                print(f"--- {path}: absent")
                continue
            body = g[b.open + 1:b.close]
            print(f"--- {path}: {len(body):,} bytes")
            print(body[:700].decode("utf-8", "replace"))
        cm = gs.locate(g, "county_manager/counties")
        first = next(gs.iter_entries(g, *cm.body))
        print("--- one county record:\n" + g[first.start:first.end][:600].decode("utf-8", "replace"))


if __name__ == "__main__":
    main()
