"""Shape of the four registries a transplant must extend (census defects 5-8), in one save.

For template_cultures, static_dynasties and static_dynasty_houses: the list length, whether it is sorted and
duplicate-free, its first items, and the template / key of the first few entries it names. For the coat name map:
size and a sample. Read-only; run with python -I <save.ck3>.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ck3_save_migrator import gamestate as gs, savefile as sf, translate as T  # noqa: E402


def ints(g, path):
    b = gs.locate(g, path)
    return [int(x) for x in g[b.open + 1:b.close].split()]


def field(g, path, i, name):
    e = dict(T.entries(g, path)).get(i)
    if e is None:
        return None
    m = re.search(rb"[\n\t]" + name + rb"=\"?([^\s\"}]+)", g[e.start:min(e.end, e.start + 3000)])
    return m and m.group(1).decode()


g = sf.read_save(sys.argv[1]).gamestate
for path, db, name in (("culture_manager/template_cultures", "culture_manager/cultures", b"culture_template"),
                       ("dynasties/static_dynasties", "dynasties/dynasties", b"key"),
                       ("dynasties/static_dynasty_houses", "dynasties/dynasty_house", b"key")):
    try:
        xs = ints(g, path)
    except Exception as ex:  # noqa: BLE001
        print(path, "unreadable:", ex)
        continue
    print(f"{path}: n={len(xs)} sorted={xs == sorted(xs)} unique={len(set(xs)) == len(xs)} "
          f"min={min(xs) if xs else None} max={max(xs) if xs else None} contiguous={xs == list(range(xs[0], xs[0] + len(xs))) if xs else None}")
    print("   first:", [(x, field(g, db, x, name)) for x in xs[:6]])
    print("   last :", [(x, field(g, db, x, name)) for x in xs[-3:]])
nm = gs.locate(g, "coat_of_arms/coat_of_arms_manager_name_map")
body = g[nm.open + 1:nm.close]
pairs = re.findall(rb"([^\s={}]+)=(\d+)", body)
print("name_map pairs", len(pairs), "sample", [(a.decode(), int(b)) for a, b in pairs[:4]],
      "raw head", body[:160])
