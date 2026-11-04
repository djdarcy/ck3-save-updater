"""U1, the rest: for one section and one field the game's re-save drops, show each entry that loses it: our value,
and the re-save's entry fields around where it was. Usage: dropped_field.py <our save> <re-save> <section path> <field>
[max examples]. Example: dropped_field.py ours.ck3 resave.ck3 tax_slot_manager/database vassals"""
import re
import sys

sys.path.insert(0, r"C:\code\ck3-save-migrator")
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator import savefile as sf  # noqa: E402


def load(path):
    try:
        return sf.read_save(path).gamestate
    except sf.UnsupportedKindError:
        raw = open(path, "rb").read()
        return raw[raw.index(b"\n") + 1:]


def entries(d, path):
    b = gs.locate(d, path)
    return {e.key: d[e.body[0]:e.body[1]] for e in gs.iter_entries(d, *b.body)}


ours, theirs = entries(load(sys.argv[1]), sys.argv[3]), entries(load(sys.argv[2]), sys.argv[3])
field = sys.argv[4].encode()
limit = int(sys.argv[5]) if len(sys.argv) > 5 else 4
pat = re.compile(rb"(?<![\w])" + field + rb"=")
shown = 0
for k, x in ours.items():
    y = theirs.get(k, b"")
    if pat.search(x) and not pat.search(y):
        m = pat.search(x)
        end = gs.match_brace(x, m.end()) + 1 if x[m.end():m.end() + 1] == b"{" else x.find(b"\n", m.end())
        print(f"== {k.decode()}: ours {x[m.start():end].decode('utf-8', 'replace')[:300]!r}")
        print(f"   re-save fields: {[f.decode() for f in re.findall(rb'(?m)^[ \t]*([a-z_]+)=', y)][:25]}")
        shown += 1
        if shown >= limit:
            break
