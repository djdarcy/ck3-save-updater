"""ethnicity_resave: does the game write `ethnicity` for the characters our migration carried without one? (2026-10-30, C2)

SAVE-FINDINGS F3: every character carried from the 1.8.1 save lacks `ethnicity` (1.8.1 had no such field); the game's
own 1.20 saves have it on every character. R24 (to write one) waits on how 1.20 chooses the value. djdarcy loaded
play7 and saved it with nothing played (the v7 re-save); this compares play7 with that re-save, character by id.

Predictions (the director's, written before the launch): the engine writes one for every character lacking it. If so,
R24 is unnecessary, or must match the engine's choice.

Reports, per section (living, dead_unprunable, characters/dead_prunable): characters in play7, lacking ethnicity
there, of those how many have one in the re-save; the distribution of the values written; and whether the value
follows culture: per culture id, how many distinct values the engine wrote, and whether the value is one of the
culture's own `ethnicities` when the save lists them (culture_manager/cultures).

Usage: python -I tests/one-offs/ethnicity_resave.py <play7.ck3> <resave.ck3>
"""
from __future__ import annotations

import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ck3_save_migrator import translate as T  # noqa: E402
from ck3_save_migrator.savefile import read_save  # noqa: E402

ETH = re.compile(rb"\n\t+ethnicity=\"?([^\"\s]+)\"?")
CULT = re.compile(rb"\n\tculture=(\d+)")
SECTIONS = ("living", "dead_unprunable", "characters/dead_prunable")


def chars(g: bytes, path: str) -> dict[int, tuple[str | None, int | None]]:
    out = {}
    for i, e in T.entries(g, path):
        body = g[e.open:e.close]
        m, c = ETH.search(body), CULT.search(body)
        out[i] = (m.group(1).decode() if m else None, int(c.group(1)) if c else None)
    return out


def culture_ethnicities(g: bytes) -> dict[int, set[str]]:
    out = {}
    for i, e in T.entries(g, "culture_manager/cultures"):
        body = g[e.open:e.close]
        m = re.search(rb"\n\t+ethnicities=\{([^}]*)\}", body)
        if m:
            out[i] = {x for x in re.findall(rb"[A-Za-z_][A-Za-z0-9_]*", m.group(1))}
    return {k: {x.decode() for x in v} for k, v in out.items()}


def main() -> None:
    a, b = read_save(sys.argv[1]).gamestate, read_save(sys.argv[2]).gamestate
    ce = culture_ethnicities(b)
    print(f"cultures in the re-save listing ethnicities: {len(ce):,}")
    for path in SECTIONS:
        ca, cb = chars(a, path), chars(b, path)
        lacking = [i for i, (eth, _) in ca.items() if eth is None]
        in_b = [i for i in lacking if i in cb]
        filled = [i for i in in_b if cb[i][0] is not None]
        print(f"\n{path}: play7 {len(ca):,} characters, {len(ca) - len(lacking):,} with ethnicity, "
              f"{len(lacking):,} without; re-save {len(cb):,}")
        print(f"   of the {len(lacking):,} without: {len(in_b):,} still in the re-save, {len(filled):,} now have one, "
              f"{len(in_b) - len(filled):,} still none")
        changed = sum(1 for i, (eth, _) in ca.items() if eth is not None and i in cb and cb[i][0] != eth)
        print(f"   of those that had one: {changed:,} changed value in the re-save")
        if not filled:
            continue
        vals = Counter(cb[i][0] for i in filled)
        print(f"   values written: {len(vals)} distinct; top: {vals.most_common(12)}")
        by_cult = defaultdict(Counter)
        in_list = not_in_list = unlisted = 0
        for i in filled:
            eth, cult = cb[i][0], cb[i][1] if cb[i][1] is not None else ca[i][1]
            by_cult[cult][eth] += 1
            if cult in ce:
                if eth in ce[cult]:
                    in_list += 1
                else:
                    not_in_list += 1
            else:
                unlisted += 1
        multi = {c: v for c, v in by_cult.items() if len(v) > 1}
        print(f"   cultures among them: {len(by_cult):,}; with more than one value written: {len(multi):,}")
        for c, v in list(multi.items())[:5]:
            print(f"      culture {c}: {dict(v.most_common(5))}  (its list: {sorted(ce.get(c, []))[:6]})")
        print(f"   value one of the culture's own ethnicities: {in_list:,}; not in its list: {not_in_list:,}; "
              f"culture lists none / unknown: {unlisted:,}")


if __name__ == "__main__":
    main()
