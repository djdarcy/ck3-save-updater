"""MEASURE (acknowledge-child, succession): why does Bruide's empire name Mael-Fothartaig as primary heir? Read-only.

djdarcy, 2026-11-16: after making Bruide ruler of the Arabian Empire (in play, from MIGRATE_TEST__ack_honest), the
game names Mael-Fothartaig 16839840 (born 981, Bruide's eldest son by birth inside the marriage) as primary heir, not
Gabran 16838491 (born 976, now Bruide's son in law). Save: _Beidh_of_Ireland_987_10_27_Bruide-issues.ck3.

For each title Bruide holds: its first heirs, its succession laws, any election. For Bruide, his sons and Conchenn:
faith, culture, age, sex, traits, and anything that blocks inheritance. Then the definitions of the laws in force,
from the game files.

Run: python -I tests/one-offs/thinking/ack_why_heir.py <save.ck3> [<game folder>]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from ck3_save_migrator import translate as T  # noqa: E402
from ck3_save_migrator.characters import CharacterIndex  # noqa: E402
from ck3_save_migrator.savefile import parse_header, parse_save  # noqa: E402

data = Path(sys.argv[1]).read_bytes()
h = parse_header(data[:64])
g = data[len(h.raw):] if h.kind == 0 else parse_save(data).gamestate
game = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("E:/SteamLibrary/steamapps/common/Crusader Kings III/game")
ix = CharacterIndex(g)
names = T.traits_lookup(g)
BRUIDE, PEOPLE = 64975, (16838491, 78307, 16839840, 79678, 81048)


def who(cid):
    c = ix.character(cid)
    return f"{cid} {c.first_name} ({'F' if c.female else 'M'}, {c.age})" if c else f"{cid} (not living)"


def field(body, key):
    m = re.search(rb"(?m)^\t+" + key + rb"=([^\n]*)", body)
    return m.group(1).decode("utf-8", "replace")[:90] if m else "-"


print("== titles Bruide holds")
laws_seen = set()
for tid, e in T.entries(g, "landed_titles/landed_titles"):
    b = g[e.open:e.close]
    if not re.search(rb"(?m)^\tholder=64975\r?$", b):
        continue
    key = field(b, b"key")
    if key[:2] not in ("e_", "k_", "h_"):
        continue
    heir = re.search(rb"(?m)^\their=\{([^}]*)\}", b)
    heirs = [int(x) for x in heir.group(1).split()] if heir else []
    laws = re.findall(rb"(?m)^\t\t?(?:succession_laws|laws)=\{([^}]*)\}", b)
    print(f"  {key}: heirs {[who(x) for x in heirs[:5]]}")
    print(f"      title laws: {[l.decode().split() for l in laws]}  election: {field(b, b'succession_election')}")
    for l in laws:
        laws_seen.update(x.decode() for x in l.split())

e = ix.living[BRUIDE]
bb = g[e.open:e.close]
rl = re.findall(rb"(?m)^\t+laws=\{([^}]*)\}", bb)
print(f"\n== Bruide: faith {field(bb, b'faith')}, culture {field(bb, b'culture')}; realm laws {[x.decode().split() for x in rl]}")
for l in rl:
    laws_seen.update(x.decode() for x in l.split())
designated = re.search(rb"(?m)^\t+designated_heir=(\d+)", bb)
print(f"   designated heir: {who(int(designated.group(1))) if designated else '-'}")
for cid in PEOPLE:
    c = ix.character(cid)
    ce = ix.living.get(cid)
    if not ce:
        print(f"  {cid}: not living")
        continue
    b = g[ce.open:ce.close]
    tr = re.search(rb"(?m)^\ttraits=\{([^}\n]*)\}", b)
    tl = [names[int(x)] for x in tr.group(1).split()] if tr else []
    print(f"  {who(cid)}: faith {field(b, b'faith')}, culture {field(b, b'culture')}, born {c.birth}, "
          f"father {c.father}, real {field(b, b'real_father')}; traits {tl}")

print("\n== law definitions (game files)")
for law in sorted(laws_seen):
    for f in (game / "common" / "laws").glob("*.txt"):
        t = f.read_text(encoding="utf-8-sig", errors="replace")
        m = re.search(r"(?m)^\t" + re.escape(law) + r" = \{", t)
        if m:
            seg = t[m.start():m.start() + 1500]
            keep = [ln.strip() for ln in seg.splitlines() if re.search(r"order_of_succession|traversal|rank|gender|faith|title_division|primary_heir|elective|cannot|limit", ln)]
            print(f"  {law} ({f.name}): {keep[:8]}")
            break
