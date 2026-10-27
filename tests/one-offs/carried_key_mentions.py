"""carried_key_mentions: for every title the transplant carried, list the sections of the 1.20 reference that name
its key, and say which of those sections do not name the carried key in the migrated save.

2026-10-27: the New Year crash was a registry the census had marked "left out by design": the reference names every
runtime title's key in `landed_titles/dynamic_templates`, and ours did not. This probe asks the same question of
every section at once, by title key (the census asked it by object id): a section of the reference that mentions a
carried title, while ours does not mention it there, is a registry or a reference the transplant may have dropped.

A section is a top-level block, or the named child of one whose children are all named (landed_titles/..., ...).
Keys are matched as tokens (`c_roma`, `x_mc_0`, `"x_mc_0"`); a title's carried key is its key in our save at
(reference id + title offset), so R15's renames and the runtime-key renames are followed.
Only title KEYS are matched: a section that names a title by numeric id is out of this probe's reach.

Usage: python -I tests/one-offs/carried_key_mentions.py <migrated.ck3> <reference.ck3> [title offset] [examples]
"""
from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator import savefile as sf  # noqa: E402

KEY = re.compile(rb'\n\tkey="?([^"\s]+)"?')
TOKEN = re.compile(rb'(?<![A-Za-z0-9_])([hbcdkex]_[A-Za-z0-9_\-]+)')


def title_keys(g: bytes) -> dict[int, str]:
    out = {}
    for e in gs.iter_entries(g, *gs.locate(g, "landed_titles/landed_titles").body):
        m = KEY.search(g, e.start, min(e.end, e.start + 200))
        if m and e.key and e.key.isdigit():
            out[int(e.key)] = m.group(1).decode()
    return out


def sections(g: bytes) -> list[tuple[str, int, int]]:
    out = []
    for name, blocks in (gs._top_index(g) or {}).items():
        for b in blocks:
            kids = list(gs.iter_entries(g, *b.body))
            named = kids and len(kids) <= 64 and all(k.key and not k.key.isdigit() for k in kids)
            if named:
                for k in kids:
                    out.append((f"{name.decode()}/{k.key.decode()}", k.open, k.close))
            else:
                out.append((name.decode(), b.open, b.close))
    return out


def mentions(g: bytes, wanted: set[str]) -> dict[str, set[str]]:
    by = defaultdict(set)
    for path, a, z in sections(g):
        for m in TOKEN.finditer(g, a, z):
            k = m.group(1).decode()
            if k in wanted:
                by[path].add(k)
    return by


def main():
    ours_p, ref_p = sys.argv[1:3]
    toff = int(sys.argv[3]) if len(sys.argv) > 3 else 12702
    nex = int(sys.argv[4]) if len(sys.argv) > 4 else 6
    g, r = sf.read_save(ours_p).gamestate, sf.read_save(ref_p).gamestate
    ok, rk = title_keys(g), title_keys(r)
    carried = {rkey: ok[rid + toff] for rid, rkey in rk.items() if rid + toff in ok}
    print(f"carried titles: {len(carried):,} of the reference's {len(rk):,}"
          f" ({sum(1 for k in carried if k.startswith('x_')):,} runtime x_)")
    rm = mentions(r, set(carried))
    om = mentions(g, set(carried.values()))
    rows = []
    for path, keys in rm.items():
        miss = sorted(k for k in keys if carried[k] not in om.get(path, ()))
        rows.append((len(miss), path, len(keys), miss))
    rows.sort(key=lambda x: (-x[0], x[1]))
    print(f"{'missing':>8} {'ref names':>9}  section")
    for n, path, total, miss in rows:
        ex = "" if not n else "   e.g. " + ", ".join(f"{k}->{carried[k]}" if carried[k] != k else k for k in miss[:nex])
        print(f"{n:>8,} {total:>9,}  {path}{ex}")


if __name__ == "__main__":
    main()
