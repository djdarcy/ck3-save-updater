"""Acceptance check A1/A2 of the own-plot-converter design (2026-11-05__09-48-21): our converter, alone, on every
plot of an updated build made before R29, against the game's day-one re-save of that build (load, pause, save).
Normalisation, applied to both sides: blank lines removed, and quotes taken off values without spaces
(the game's writer does both across the whole save). Nothing else: no key-order normalisation.
Usage: python -I scheme_identity.py <build.ck3> <re-save.ck3> [max mismatches to print]"""
import difflib
import re
import sys
from collections import Counter

sys.path.insert(0, r"C:\code\ck3-save-migrator")
from ck3_save_migrator import savefile as sf, gamestate as gs  # noqa: E402
from ck3_save_migrator.rules import to_1_20 as r  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def load(p):
    try:
        return sf.read_save(p).gamestate
    except sf.UnsupportedKindError:
        raw = open(p, "rb").read()
        return raw[raw.index(b"\n") + 1:]


def inner(d):
    b = gs.locate(d, "schemes/active")
    return {e.key: d[e.open + 1:e.close] for e in gs.iter_entries(d, *b.body) if e.key}


def norm(t):
    t = re.sub(rb'="([^"\s]+)"', rb"=\1", t)
    t = re.sub(rb"(?m)(\S)(\t+)\}$", rb"\1\n\2}", t)    # the game's writer: "modifier=X\t\t\t}" on one line
    return b"\n".join(line for line in t.split(b"\n") if line.strip())


old, new = inner(load(sys.argv[1])), inner(load(sys.argv[2]))
show = int(sys.argv[3]) if len(sys.argv) > 3 else 3
paired = [k for k in old if k in new]
same, bad, status = 0, [], Counter()
for k in paired:
    ind, f = r.scheme_fields(old[k])
    assert r.is_old_scheme(f), k
    conv = r.convert_old_scheme(f, ind)
    ours = norm(r.scheme_text(conv, ind))
    theirs = norm(new[k])
    st = re.search(rb"status=(\w+)", new[k]).group(1)
    status[(st, dict(conv).get(b"status") == b"status=" + st)] += 1
    if ours == theirs:
        same += 1
    else:
        bad.append((k, ours, theirs))
def var_split(t):
    """(text without the variables store's entries, [entries in order]); entries found with the brace matcher."""
    v = t.find(b"variables={")
    if v < 0:
        return t, []
    d0 = t.find(b"data={", v)
    if d0 < 0:
        return t, []
    open_ = d0 + len(b"data=")
    close = gs.match_brace(t, open_)
    items, i = [], open_ + 1
    while (j := t.find(b"{", i, close)) >= 0:
        e = gs.match_brace(t, j)
        items.append(t[j:e + 1])
        i = e + 1
    return t[:open_ + 1] + t[close:], items


def flag(item):
    m = re.search(rb"flag=(\S+)", item)
    return m.group(1) if m else b""


def var_items(t):
    rest, items = var_split(t)
    return Counter(items), rest


reordered = [(k, o, t) for k, o, t in bad if var_items(o) == var_items(t)]
bad = [x for x in bad if x not in reordered]
alpha = sum(1 for _, _, t in reordered if [flag(x) for x in var_split(t)[1]] == sorted(flag(x) for x in var_split(t)[1]))
print(f"of the reordered, the game's order is alphabetical by flag on {alpha}/{len(reordered)}")
multi = Counter()
for k in paired:
    o, t = var_split(norm(old[k]))[1], var_split(norm(new[k]))[1]
    if len(t) >= 2:
        fo, ft = [flag(x) for x in o], [flag(x) for x in t]
        multi["same order" if fo == ft else "reversed" if fo[::-1] == ft else
              "first kept, rest reversed" if fo[:1] + fo[1:][::-1] == ft else "other"] += 1
print("plots with 2+ variables, the game's order vs ours:", dict(multi))
if len(sys.argv) > 4 and reordered:
    for k, o, t in reordered[:4]:
        print(k.decode(), "game:", [flag(x).decode() for x in var_split(t)[1]], "ours:",
              [flag(x).decode() for x in var_split(o)[1]])
print(f"identical {same}/{len(paired)}; same content with the variables store in another order {len(reordered)}; "
      f"other {len(bad)}  (reconcile {same}+{len(reordered)}+{len(bad)}={same + len(reordered) + len(bad)})")
print("status (game's, ours agrees):", dict(status))
if len(sys.argv) > 4 and bad:                         # dump the first mismatch in full
    k, o, t = bad[0]
    print(f"--- {k.decode()} OURS\n{o.decode('latin-1')}\n--- GAME\n{t.decode('latin-1')}")
kinds = Counter()
for k, ours, theirs in bad:
    diff = [ln for ln in difflib.unified_diff(theirs.decode("latin-1").split("\n"), ours.decode("latin-1").split("\n"),
                                              lineterm="", n=0)
            if ln[:1] in "+-" and not ln.startswith(("+++", "---"))]
    kinds[tuple(diff[:4])] += 1
print("(- is the game's line, + is ours)")
for kind, n in kinds.most_common(show):
    print(n, "x", list(kind))
