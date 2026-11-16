"""MEASURE (acknowledge-child): did the game's own save keep the edit? Read-only.

djdarcy loaded MIGRATE_TEST__ack_honest.ck3 (acknowledge-child 16838491 64975 honest) and saved it from the game as
_Beidh_of_Ireland_987_10_27_ack_honest.ck3 (2026-11-16). This reads that save (a normal or a plain-text one) and checks
what the edit set.

PREDICTION, written before reading: Bruide 64975 still lists Gabran 16838491 (and Conchenn 78307); Gabran's own entry
keeps real_father=57756; he carries no bastard-family trait; the secret about him is secret_disputed_heritage,
owner 65171, participants 65171 and 57756.

Run: python -I tests/one-offs/thinking/ack_check_resave.py <save.ck3>
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator import translate as T  # noqa: E402
from ck3_save_migrator.characters import CharacterIndex  # noqa: E402
from ck3_save_migrator.savefile import parse_header, parse_save  # noqa: E402

data = Path(sys.argv[1]).read_bytes()
h = parse_header(data[:64])
g = data[len(h.raw):] if h.kind == 0 else parse_save(data).gamestate
print(f"header kind {h.kind:02x}; date {re.search(rb'(?m)^date=([\d.]+)', g).group(1).decode()}")
ix = CharacterIndex(g)
names = T.traits_lookup(g)
results = []
for cid in (16838491, 78307):
    c = ix.character(cid)
    results.append((f"{cid} father is 64975", c is not None and c.father == 64975, c and c.father))
    results.append((f"{cid} mother is 65171", c is not None and c.mother == 65171, c and c.mother))
e = ix.living[16838491]
body = g[e.open:e.close]
real = re.search(rb"(?m)^\t\treal_father=(\d+)", body)
results.append(("Gabran keeps real_father=57756", bool(real) and real.group(1) == b"57756", real and real.group(1).decode()))
tr = re.search(rb"(?m)^\ttraits=\{([^}\n]*)\}", body)
mine = [names[int(x)] for x in tr.group(1).split()] if tr else []
bad = [t for t in mine if t in ("bastard", "wild_oat", "legitimized_bastard", "disputed_heritage")]
results.append(("Gabran has no bastard-family trait", not bad, bad or mine))
found = None
for s in gs.iter_entries(g, *gs.locate(g, "secrets/secrets").body):
    sb = g[s.open:s.close]
    if re.search(rb"identity=16838491\s", sb):
        found = sb.decode("utf-8", "replace").replace("\n", " ").replace("\t", "")[:160]
results.append(("the secret about him is disputed heritage", bool(found) and "secret_disputed_heritage" in found, found))
bl = ix.living.get(64975)
lst = re.compile(rb"(?m)^\t\tchild=\{([^}\n]*)\}").search(g, bl.open, bl.close) if bl else None
results.append(("Bruide's child list", bool(lst) and b"16838491" in lst.group(1).split(), lst and lst.group(0).decode().strip()))
for name, ok, seen in results:
    print(f"  {'PASS' if ok else 'FAIL'}  {name:<44} {seen}")
