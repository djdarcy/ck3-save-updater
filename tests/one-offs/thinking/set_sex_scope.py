"""MEASURE (S2 step 1, static part): what does a character's sex look like in a 1.20 save, and what else names it?

DWP 2026-11-06__21-37-30 (save-edits front door), build step 1: "the female=yes key's place; what else the game
recomputes on load ...; whether the face reads as the other sex". This script does the part that needs no game:
  1  the living characters named <first name> (Conchenn, the founding case), each with id, age, house, sex;
  2  where `female=yes` sits in an entry (depth, neighbours), and how many living characters carry it;
  3  every other place in the save that holds a sex-dependent value for that character (searched by id):
     spouse / betrothal links, the title succession laws (male/equal/female primogeniture), DNA (gender-specific
     genes need the game's gene file to read -- only the DNA's length is shown here).
Known answer: the count of `female=yes` among living characters must be between 30% and 70% of them.

Run: python -I tests/one-offs/thinking/set_sex_scope.py <save.ck3> <first name>
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from ck3_save_migrator import translate as T  # noqa: E402
from ck3_save_migrator.savefile import read_save  # noqa: E402

save, first = Path(sys.argv[1]), sys.argv[2].encode()
g = read_save(save).gamestate
living = list(T.entries(g, "living"))
fem = 0
hits = []
for cid, e in living:
    body = g[e.open:e.close]
    # an entry's own keys have one tab (the entries of `living` start at column 0; a first try with three tabs
    # found 0 women among 44,553 characters -- the known-answer check caught it)
    is_f = re.search(rb"(?m)^\tfemale=yes", body) is not None
    fem += is_f
    if re.search(rb'(?m)^\tfirst_name="' + re.escape(first) + rb'"', body):
        hits.append((cid, e, is_f))
print(f"living: {len(living):,}; female=yes: {fem:,} ({fem / max(1, len(living)):.0%})")
print(f"living named {first.decode()}: {len(hits)}")
for cid, e, is_f in hits:
    body = g[e.open:e.close]
    top = [ln for ln in body.split(b"\n") if ln.startswith(b"\t") and not ln.startswith(b"\t\t")]
    print(f"\n--- character {cid.decode() if isinstance(cid, bytes) else cid} ({'female' if is_f else 'male'}),"
          f" {len(body):,} bytes; depth-1 keys in order:")
    print("   ", " ".join(ln.strip().split(b"=")[0].decode() for ln in top))
    for ln in top:
        if re.match(rb"\t(female|birth|first_name|dynasty_house|sexuality|dna)\b", ln):
            print("   ", ln.strip()[:120].decode(errors="replace"))
    idb = cid if isinstance(cid, bytes) else str(cid).encode()
    refs = [(m.start(), g[max(0, m.start() - 60):m.start() + 30]) for m in
            re.finditer(rb"(?<![\d.])" + re.escape(idb) + rb"(?![\d.])", g)]
    print(f"    the id appears {len(refs):,} times in the gamestate; context of the first 12 outside its entry:")
    for pos, ctx in [r for r in refs if not (e.open <= r[0] <= e.close)][:12]:
        print("     ", pos, ctx.replace(b"\n", b" | ").replace(b"\t", b"")[-80:].decode(errors="replace"))
