"""variant_dynamic_templates: a diagnostic copy of a migrated save in which every runtime (x_) title the transplant
carried is registered in landed_titles/dynamic_templates, as the game registers the runtime titles it creates.

2026-10-27: 1.20 keeps `landed_titles/dynamic_templates={ { key="x_mc_0" tier=duchy dyn=yes } ... }`; a runtime
title whose key is not listed there is rejected at load ("x_mc_1932 is not a valid title template") and destroyed in
play, and its mercenary company is left pointing at it, which crashes the game's yearly company pass. The transplant
carried 167 companies' titles without registering them. The tier (and any other field) is taken from the reference's
own entry for the title's reference key. Keys are left as the save has them. Never a migration.

Usage: python -I tests/one-offs/variant_dynamic_templates.py <migrated.ck3> <reference.ck3> <out.ck3> [title offset]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator import savefile as sf  # noqa: E402

KEY = re.compile(rb'\n\tkey="?([^"\s]+)"?')
TPL = re.compile(rb'\{\s*key="?([^"\s}]+)"?([^{}]*)\}')


def keys(g: bytes) -> dict[int, str]:
    out = {}
    for e in gs.iter_entries(g, *gs.locate(g, "landed_titles/landed_titles").body):
        m = KEY.search(g, e.start, min(e.end, e.start + 200))
        if m and e.key and e.key.isdigit():
            out[int(e.key)] = m.group(1).decode()
    return out


def main():
    src, ref_p, out = sys.argv[1:4]
    toff = int(sys.argv[4]) if len(sys.argv) > 4 else 12702
    save = sf.read_save(src)
    g, r = save.gamestate, sf.read_save(ref_p).gamestate
    ok, rk = keys(g), keys(r)
    rdt = gs.locate(r, "landed_titles/dynamic_templates")
    ref_tpl = {m.group(1).decode(): m.group(2).strip() for m in TPL.finditer(r, rdt.open, rdt.close)}
    dt = gs.locate(g, "landed_titles/dynamic_templates")
    have = {m.group(1).decode() for m in TPL.finditer(g, dt.open, dt.close)}
    adds, missing_ref = [], 0
    for rid, rkey in rk.items():
        if not rkey.startswith("x_"):
            continue
        okey = ok.get(rid + toff)
        if okey is None or okey in have:
            continue
        rest = ref_tpl.get(rkey)
        if rest is None:
            missing_ref += 1
            continue
        adds.append(b'{ key="' + okey.encode() + b'" ' + rest + b" } ")
        have.add(okey)
    at = g.rfind(b"}", dt.open, dt.close + 1)        # inside the block, before its closing brace
    save.replace_range(dt.close, dt.close, b" ".join(adds))
    sf.write_save(save, out, force=True)
    print(f"registered {len(adds)} carried runtime titles in dynamic_templates "
          f"(reference entry missing for {missing_ref}); wrote {out}")


if __name__ == "__main__":
    main()
