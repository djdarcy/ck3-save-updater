"""variant_mc_keys: a diagnostic copy of a save in which every mercenary company's title is keyed x_mc_<company id>,
as the vanilla 1.20 reference keys all 562 of its companies.

2026-10-27: our carried companies' titles were renumbered to "the next free x_mc_ number" (x_mc_1821...); the game
rejects exactly those 167 keys at load ("is not a valid title template"), destroys such a title when its holder
leaves no valid heir (destroy_if_invalid_heir), and its yearly pass then follows the company's dangling title id into
the shared "none" title and crashes (ck3+0x2ac4bbe). This tests the fix before it goes into the tool. A company
title whose wanted key is held by a title that is not a company title is left as is, and reported.

Usage: python -I tests/one-offs/variant_mc_keys.py <in.ck3> <out.ck3>
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator import savefile as sf  # noqa: E402

KEY = re.compile(rb'\n\tkey="?([^"\s]+)"?')


def main():
    src, out = sys.argv[1:3]
    save = sf.read_save(src)
    g = save.gamestate
    tkey, tspan = {}, {}
    for e in gs.iter_entries(g, *gs.locate(g, "landed_titles/landed_titles").body):
        m = KEY.search(g, e.start, min(e.end, e.start + 200))
        if m and e.key:
            tkey[e.key.decode()] = m.group(1).decode()
            tspan[e.key.decode()] = (m.start(1), m.end(1))
    company_titles = {}
    for e in gs.iter_entries(g, *gs.locate(g, "mercenary_company_manager/mercenary_companies").body):
        t = re.search(rb"\n\t+title=(\d+)", g[e.start:e.end])
        if t:
            company_titles[t.group(1).decode()] = int(e.key)
    held_by_other = {k for i, k in tkey.items() if i not in company_titles}
    edits, renamed, blocked = [], 0, []
    for tid, cid in company_titles.items():
        want = f"x_mc_{cid & 0xFFFFFF}" if cid >= 0x1000000 else f"x_mc_{cid}"
        have = tkey.get(tid)
        if have is None or have == want:
            continue
        if want in held_by_other:
            blocked.append(f"{tid} {have} -> {want} (held by a non-company title)")
            continue
        s, e = tspan[tid]
        edits.append((s, e, want.encode()))
        renamed += 1
    for s, e, rep in sorted(edits, reverse=True):
        save.replace_range(s, e, rep)
    sf.write_save(save, out, force=True)
    print(f"company titles {len(company_titles)}; renamed {renamed}; blocked {len(blocked)} {blocked[:5]}; wrote {out}")


if __name__ == "__main__":
    main()
