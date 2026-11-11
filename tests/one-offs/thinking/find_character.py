"""MEASURE (set-sex, step 0): find one character among the living by first name, with what tells them apart.

For the save editor's set-sex measurement (ruling 2026-11-08__17-02-55, addendum 22:43, measurement (a)): the founding
case is "Conchenn nic Bruide, 7" and 30 living characters are named Conchenn. This lists every living character with
the given first name: id, sex, birth date (age at the save's date), house id and the house's name/key, father, mother.
Read-only: it never writes.

Known answer: the count printed must equal set_sex_scope.py's "living named <name>" (30 for Conchenn on v12).

Run: python -I tests/one-offs/thinking/find_character.py <save.ck3> <first name>
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
s = read_save(save)
g = s.gamestate
date = re.search(rb'(?m)^date=(\d+)\.(\d+)\.(\d+)', g)
year = int(date.group(1)) if date else None


def val(body: bytes, key: bytes) -> str:
    m = re.search(rb'(?m)^\t' + key + rb'=("?)([^"\n]*)\1', body)
    return m.group(2).decode("utf-8", "replace") if m else ""


houses = {}
for hid, e in T.entries(g, "dynasties/dynasty_house"):
    body = g[e.open:e.close]
    houses[hid.decode() if isinstance(hid, bytes) else str(hid)] = (val(body, b"name") or val(body, b"key"))

hits = []
for cid, e in T.entries(g, "living"):
    body = g[e.open:e.close]
    if not re.search(rb'(?m)^\tfirst_name="' + re.escape(first) + rb'"', body):
        continue
    fam = re.search(rb'(?m)^\tfamily_data=\{(.*?)^\t\}', body, re.S)
    fd = fam.group(1) if fam else b""
    father = re.search(rb'father=(\d+)', body)
    mother = re.search(rb'mother=(\d+)', body)
    birth = val(body, b"birth")
    age = (year - int(birth.split(".")[0])) if (year and birth) else None
    house = val(body, b"dynasty_house")
    hits.append((cid.decode() if isinstance(cid, bytes) else str(cid), "F" if re.search(rb"(?m)^\tfemale=yes", body) else "M",
                 birth, age, house, houses.get(house, "?"), father.group(1).decode() if father else "-",
                 mother.group(1).decode() if mother else "-"))
print(f"save date year: {year}; living named {first.decode()}: {len(hits)}")
for h in sorted(hits, key=lambda h: h[3] if h[3] is not None else 999):
    print(f"  {h[0]:>10} {h[1]} born {h[2]:<10} age {h[3]!s:>3}  house {h[4]:>10} {h[5]!r:<40} father {h[6]:>10} mother {h[7]:>10}")
