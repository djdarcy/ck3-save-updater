"""MEASURE (a "legitimize as the spouse's own" edit), the population: how does the game itself write a child whose
legal father and real father differ? Read-only.

For every kept character (living and dead_unprunable) whose entry has `real_father=`: the legal parents (who lists
them in child={ }), whether the legal father is the real father, and which bastard-family traits they carry; then
the secrets about such children, by type. The target state of the edit is the class "a legal father who is not the
real father, no bastard trait": if the game writes that class itself, the edit can copy it exactly.

PREDICTION, written before the run: that class exists (children of adultery the husband believes are his), with no
bastard trait and a secret of the illegitimate-child kind; children with real_father and no legal father carry
bastard or wild_oat, like Gabran.
KNOWN ANSWER: Gabran 16838491 must fall in "no legal father" with wild_oat.

Run: python -I tests/one-offs/thinking/legitimize_population.py <save.ck3>
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

g = read_save(Path(sys.argv[1])).gamestate
names = T.traits_lookup(g)
BASTARDS = {"bastard", "wild_oat", "legitimized_bastard", "disputed_heritage", "child_of_concubine"}
ix = CharacterIndex(g)
REAL = re.compile(rb"(?m)^\t\treal_father=(\d+)")
TRAITS = re.compile(rb"(?m)^\ttraits=\{([^}]*)\}")
classes, examples = Counter(), {}
gabran = None
for space in (ix.living, ix.dead):
    for cid, e in space.items():
        b = g[e.open:e.close]
        m = REAL.search(b)
        if not m:
            continue
        real = int(m.group(1))
        father, mother = ix.parents.get(cid, (None, None))
        tr = TRAITS.search(b)
        mine = sorted({names[int(x)] for x in (tr.group(1).split() if tr else []) if int(x) < len(names)} & BASTARDS)
        legal = "no legal father" if father is None else ("legal father IS the real father" if father == real
                                                          else "legal father is NOT the real father")
        key = (legal, ",".join(mine) or "no bastard trait")
        classes[key] += 1
        examples.setdefault(key, cid)
        if cid == 16838491:
            gabran = key
total = sum(classes.values())
print(f"characters with real_father: {total}")
for (legal, tr), n in sorted(classes.items(), key=lambda kv: -kv[1]):
    print(f"  {n:>5}  {legal:<36} {tr:<28} e.g. {examples[(legal, tr)]}")
print(f"KNOWN ANSWER Gabran: {gabran} (want ('no legal father', 'wild_oat'))")

types = Counter(m.group(1).decode() for m in re.finditer(rb'type="(secret_[a-z_]*(?:illegit|bastard|herit|child)[a-z_]*)"', g))
print("secret types about parentage:", dict(types))

# which secret, and whose, goes with each class: index the parentage secrets by their target
sec = gs.locate(g, "secrets/secrets")
by_target = {}
for e in gs.iter_entries(g, *sec.body):
    b = g[e.open:e.close]
    t = re.search(rb'type="(secret_disputed_heritage|secret_unmarried_illegitimate_child)"', b)
    tg = re.search(rb"target=\{\s*type=char\s*identity=(\d+)", b)
    if t and tg:
        owner = re.search(rb"(?m)^\t+owner=(\d+)", b)
        parts = re.search(rb"participants=\{([^}]*)\}", b)
        by_target.setdefault(int(tg.group(1)), []).append(
            (t.group(1).decode(), int(owner.group(1)) if owner else None,
             [int(x) for x in parts.group(1).split()] if parts else []))
shape = Counter()
for space in (ix.living, ix.dead):
    for cid, e in space.items():
        m = REAL.search(g[e.open:e.close])
        if not m:
            continue
        real = int(m.group(1))
        father, mother = ix.parents.get(cid, (None, None))
        if father is None or father == real:
            continue
        for kind, owner, parts in by_target.get(cid, [("none", None, [])]):
            who = "owner=mother" if owner == mother else "owner=real father" if owner == real else f"owner=other"
            shape[(kind, who, "participants=mother+real" if set(parts) == {mother, real} else "participants other")] += 1
print("legal father is NOT the real father -> their secret:")
for k, n in shape.most_common():
    print(f"  {n:>5}  {k}")
