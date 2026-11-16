"""MEASURE (a "legitimize as the spouse's own" edit), static and read-only.

Before designing an edit that makes a bastard the legitimate child of his mother's husband, read what the save holds
for the people involved, and how the save records the things the game would change: the bastard traits, the legal
and real father, the house, adoption, and secrets about parentage.

Founding case: Gabran 16838491 ("Gabran mag Aelfweard"), mother E_lfweard 65171, her husband Bruide 64975, and
their child Conchenn 78307 (finding 2026-11-09__01-52-22: Conchenn's parents are known only from their child={ }
lists).

PREDICTION, written before the run:
  - Gabran carries the trait `bastard` (or `wild_oat` if his faith recognises no bastards), and his house is his
    mother's (the game's set_parent_house_effect gives a known bastard the mother's house in some cases).
  - E_lfweard lists him in child={ }; no man does, or another man does (his real father).
  - Bruide's child list holds Conchenn and not Gabran.
  - There may be a secret about him (a bastard or "disputed heritage" secret).
KNOWN ANSWER (validates the child-list reading): Conchenn's father must come out as 64975 and her mother 65171.

Run: python -I tests/one-offs/thinking/legitimize_probe.py <save.ck3> [id ...]
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator import translate as T  # noqa: E402
from ck3_save_migrator.characters import CharacterIndex  # noqa: E402
from ck3_save_migrator.savefile import read_save  # noqa: E402

save = Path(sys.argv[1])
ids = [int(x) for x in sys.argv[2:]] or [16838491, 65171, 64975, 78307]
g = read_save(save).gamestate
names = T.traits_lookup(g)
print(f"traits_lookup: {len(names)} names; bastard-family positions:",
      {n: i for i, n in enumerate(names) if n in ("bastard", "wild_oat", "legitimized_bastard", "disputed_heritage",
                                                   "child_of_concubine", "bastard_founder")})
ix = CharacterIndex(g)
living, dead = ix.living, ix.dead
c = ix.character(78307)
print(f"KNOWN ANSWER Conchenn: father {c.father} (want 64975), mother {c.mother} (want 65171) ->",
      "OK" if (c.father, c.mother) == (64975, 65171) else "WRONG")


def body_of(cid: int) -> bytes:
    e = living.get(cid) or dead.get(cid)
    return g[e.open:e.close] if e else b""


def listed_by(cid: int) -> list[int]:
    out = []
    pat = re.compile(rb"(?m)^\t\tchild=\{([^}]*)\}")
    for space in (living, dead):
        for pid, e in space.items():
            m = pat.search(g, e.open, e.close)
            if m and str(cid).encode() in m.group(1).split():
                out.append(pid)
    return out


for cid in ids:
    b = body_of(cid)
    where = "living" if cid in living else "dead" if cid in dead else "NOT FOUND"
    print(f"\n===== {cid} ({where}) {len(b)} bytes")
    tr = re.search(rb"(?m)^\ttraits=\{([^}]*)\}", b)
    if tr:
        print("  traits:", [names[int(x)] if int(x) < len(names) else f"?{x}" for x in tr.group(1).split()])
    for key in (b"first_name", b"nickname", b"birth", b"female", b"dynasty_house", b"culture", b"faith", b"sexuality"):
        m = re.search(rb"(?m)^\t" + key + rb"=([^\n]*)", b)
        if m:
            print(f"  {key.decode()}: {m.group(1).decode('utf-8', 'replace')[:80]}")
    fam = re.search(rb"(?m)^\tfamily_data=\{\n(.*?)^\t\}", b, re.S)
    print("  family_data:", (fam.group(1).decode("utf-8", "replace").replace("\n", " | ")[:400] if fam else "-"))
    for key in (b"real_father", b"adopt", b"legit", b"bastard", b"claim", b"heir"):
        hits = sorted({m.group(0).decode()[:60] for m in re.finditer(rb"[\w.]*" + key + rb"[\w.]*=[^\n{]{0,30}", b)})
        if hits:
            print(f"  keys with {key.decode()!r}:", hits[:8])
    print("  listed in child={ } by:", listed_by(cid))
    house = re.search(rb"(?m)^\tdynasty_house=(\d+)", b)
    if house:
        print(f"  house {house.group(1).decode()}: {ix.houses.get(house.group(1).decode(), '?')!r}")

# how the save records parentage, across the whole population
real = Counter()
for space in (living, dead):
    for pid, e in space.items():
        bb = g[e.open:e.close]
        for key in (b"real_father=", b"adopted", b"adoptive", b"adopter"):
            if key in bb:
                real[key.decode()] += 1
print("\ncharacters whose entry holds:", dict(real))
for key in (rb"\badopt\w*=", rb"\breal_father=", rb"\blegitimi\w*="):
    found = Counter(m.group(0) for m in re.finditer(key, g))
    print(f"  anywhere in the save, {key.decode()!r}:", dict(found.most_common(5)))

# secrets about the founding case
try:
    sec = gs.locate(g, "secrets/secrets")
    n = 0
    for e in gs.iter_entries(g, *sec.body):
        bb = g[e.open:e.close]
        if any(re.search(rb"(?m)^\t+(target|owner)=" + str(x).encode() + rb"\b", bb) for x in ids[:3]):
            print("  secret:", bb.decode("utf-8", "replace").replace("\n", " ")[:220])
            n += 1
    print(f"secrets naming {ids[:3]} as owner or target: {n}")
except gs.GamestateError:
    print("no secrets database")
