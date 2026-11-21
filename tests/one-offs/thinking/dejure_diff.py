"""Which counties sit de jure in a different duchy than a fresh game puts them, and why? (Goal 2026-11-20__16-02-08
S4, after djdarcy's note: fix the 9 steppe duchies that are ours, and the 11 new 1.21 duchies if nothing explains them.)

For each county key in both saves: its de jure duchy key in the campaign and in the reference. Prints the counties
that differ, grouped by the reference's duchy, with whether that duchy exists in the campaign and how many counties it
holds there, so the 9 empty steppe duchies (ours to fix) can be told apart from drift by play elsewhere.

Usage: python -I tests/one-offs/thinking/dejure_diff.py <ref.ck3> <campaign.ck3> [duchy_key ...]
Works on 1.20 and 1.21 saves (1.21 writes "type=...\\tkey=..." on one line; 1.20 a line of its own).
"""
import collections
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator.savefile import read_save  # noqa: E402


def titles(g):
    by_id, by_key = {}, {}
    for e in gs.iter_entries(g, *gs.locate(g, "landed_titles/landed_titles").body):
        if not e.key:
            continue
        b = g[e.open:e.close]
        k = re.search(rb'\tkey="?([a-z_0-9]+)', b)
        if k:
            by_id[e.key.decode()] = k.group(1).decode()
            by_key[k.group(1).decode()] = b
    return by_id, by_key


def county_duchy(g):
    by_id, by_key = titles(g)
    out = {}
    for k, b in by_key.items():
        if k.startswith("c_"):
            m = re.search(rb"\tde_jure_liege=(\d+)", b)
            out[k] = by_id.get(m.group(1).decode()) if m else None
    return out, by_key


def main(ref_path, camp_path, *focus):
    ref, _ = county_duchy(read_save(ref_path).gamestate)
    camp, camp_titles = county_duchy(read_save(camp_path).gamestate)
    common = [c for c in ref if c in camp]
    diff = [(c, camp[c], ref[c]) for c in common if camp[c] != ref[c]]
    held_in_camp = collections.Counter(d for d in camp.values() if d)
    print(f"counties in both: {len(common)}; de jure duchy differs: {len(diff)}")
    by_ref = collections.defaultdict(list)
    for c, cd, rd in diff:
        by_ref[rd].append((c, cd))
    rows = sorted(by_ref.items(), key=lambda kv: -len(kv[1]))
    empty = [d for d, _ in rows if d and d in camp_titles and held_in_camp[d] == 0]
    missing = [d for d, _ in rows if d and d not in camp_titles]
    print(f"reference duchies involved: {len(rows)}; of them absent from the campaign: {len(missing)}; "
          f"present but with no counties there: {len(empty)}")
    for d, cs in rows[:40]:
        tag = "ABSENT" if d not in camp_titles else ("EMPTY" if held_in_camp[d] == 0 else f"{held_in_camp[d]} held")
        if focus and d not in focus:
            continue
        print(f"  {d} [{tag}]: {len(cs)} counties, now in {sorted(set(x for _, x in cs))[:4]}: {[c for c, _ in cs][:5]}")


if __name__ == "__main__":
    main(*sys.argv[1:])
