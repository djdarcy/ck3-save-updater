"""Do title lieges and vassal contracts move in lock step? (djdarcy 2026-11-05: "Have we insured when we rebind all
of these aspects that we've always done both edits so the two always move in lock step?")

For every living ruler (a character with a domain): his primary title (the first domain entry) and its de facto
liege, whose holder is his "title liege"; his vassal contract (vassal=him), whose liege is his "contract liege".
Classifies each ruler:
  agree        title liege holder == contract liege, and the liege lists the contract
  unlisted     they agree, but the liege's landed_data/vassal_contracts does not list the contract (deleted on load)
  title only   a title liege, no contract
  contract only  a contract, no title liege (the Kubasar case)
  disagree     both, naming different people
  independent  neither
A title liege held by the ruler himself counts as none (his own higher title). Known answer: the player is
"independent" or "agree" (he is a top liege).
Usage: python -I liege_agreement.py <save.ck3> [player id] [max examples]"""
import re
import sys
from collections import Counter, defaultdict

sys.path.insert(0, r"C:\code\ck3-save-migrator")
from ck3_save_migrator import savefile as sf, gamestate as gs  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
g = sf.read_save(sys.argv[1]).gamestate
show = int(sys.argv[3]) if len(sys.argv) > 3 else 5
b = gs.locate(g, "landed_titles/landed_titles")
holder, liege, key = {}, {}, {}
for e in gs.iter_entries(g, *b.body):
    body = g[e.open:min(e.close, e.open + 4096)]
    i = int(e.key)
    k = re.search(rb'\n\tkey="?([\w-]+)', body)
    key[i] = k.group(1).decode() if k else "?"
    h = re.search(rb"\n\tholder=(\d+)", body)
    holder[i] = int(h.group(1)) if h else None
    lg = re.search(rb"\n\tde_facto_liege=(\d+)", body)
    liege[i] = int(lg.group(1)) if lg else None
lv = gs.find_section(g, "living")
seg = g[lv.start:lv.end]
primary, lists = {}, {}
for m in re.finditer(rb"(?m)^(\d+)=\{", seg):
    end = gs.match_brace(seg, m.end() - 1)
    body = seg[m.start():end]
    d = re.search(rb"\n\t\tdomain=\{([^}]*)\}", body)
    ids = d.group(1).split() if d else []
    if ids:
        primary[int(m.group(1))] = int(ids[0])
    vc = re.search(rb"\n\t\tvassal_contracts=\{([^}]*)\}", body)
    lists[int(m.group(1))] = {int(x) for x in vc.group(1).split()} if vc else set()
contract = {}
for path in ("vassal_contracts/active", "vassal_contracts/database"):
    try:
        cb = gs.locate(g, path)
    except gs.GamestateError:
        continue
    for e in gs.iter_entries(g, *cb.body):
        body = g[e.open:e.close]
        v, lg = re.search(rb"\n\t+vassal=(\d+)", body), re.search(rb"\n\t+liege=(\d+)", body)
        if v and lg:
            contract[int(v.group(1))] = (int(e.key), int(lg.group(1)))
kinds, ex = Counter(), defaultdict(list)
for c, p in primary.items():
    tl = liege.get(p)
    th = holder.get(tl) if tl is not None else None
    if th == c:
        th = None                                      # his own higher title
    ct = contract.get(c)
    if th is None and ct is None:
        k = "independent"
    elif th is not None and ct is None:
        k = "title only"
    elif th is None:
        k = "contract only"
    elif th != ct[1]:
        k = "disagree"
    else:
        k = "agree" if ct[0] in lists.get(ct[1], set()) else "unlisted"
    kinds[k] += 1
    if len(ex[k]) < show:
        ex[k].append(f"{c} primary {key.get(p)} title-liege {key.get(tl)}->{th} contract {ct}")
print(f"{sys.argv[1].rsplit('/', 1)[-1]}: {len(primary)} rulers:", dict(kinds.most_common()))
for k in ("contract only", "title only", "disagree", "unlisted"):
    for line in ex[k]:
        print(f"  {k:13} {line}")
