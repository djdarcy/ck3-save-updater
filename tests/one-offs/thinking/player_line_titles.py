"""#6 criterion 1: "No title whose key is absent from the old save is held by the player's line after migration".
Reads the played character, their house and dynasty in the updated save, then every held title. Reports the titles
the player holds in the old and the updated save (they should match), and any title whose key the old save lacks
that someone of the player's house or dynasty holds (should be none, or only ones the report names).
Known answer: the old save's player (50822) holds titles in the old save.
Usage: python -I player_line_titles.py <old gamestate (extracted)> <updated .ck3>"""
import re
import sys

sys.path.insert(0, r"C:\code\ck3-save-migrator")
from ck3_save_migrator import savefile as sf, gamestate as gs  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def titles(d):
    """{key: holder id or None} over landed_titles."""
    b = gs.locate(d, "landed_titles/landed_titles")
    out = {}
    for e in gs.iter_entries(d, *b.body):
        body = d[e.open:e.close]
        k = re.search(rb'(?m)^\tkey="?([\w-]+)', body)
        h = re.search(rb"(?m)^\tholder=(\d+)", body)
        if k:
            out[k.group(1).decode()] = h.group(1).decode() if h else None
    return out


def player(d):
    m = re.search(rb"(?m)^played_character=\{\s*name=\"?[^\n]*\n\s*character=(\d+)", d)
    return m.group(1).decode()


def house_and_dynasty(d):
    """{character: house} for living characters, and {house: dynasty}."""
    lv = gs.find_section(d, "living")
    ch = {m.group(1).decode(): m.group(2).decode()
          for m in re.finditer(rb"(?ms)^(\d+)=\{.*?^\tdynasty_house=(\d+)", d[lv.start:lv.end])}
    hs = gs.locate(d, "dynasties/dynasty_house")
    hd = {}
    for e in gs.iter_entries(d, *hs.body):
        m = re.search(rb"(?m)^\t{1,2}dynasty=(\d+)", d[e.open:e.close])
        if m:
            hd[e.key.decode()] = m.group(1).decode()
    return ch, hd


old = open(sys.argv[1], "rb").read()
new = sf.read_save(sys.argv[2]).gamestate
p_old, p_new = player(old), player(new)
t_old, t_new = titles(old), titles(new)
held_old = sorted(k for k, h in t_old.items() if h == p_old)
held_new = sorted(k for k, h in t_new.items() if h == p_new)
assert held_old, "known answer failed: the player holds nothing in the old save"
print(f"player old {p_old}, new {p_new}; titles held: old {len(held_old)}, new {len(held_new)}; "
      f"same set: {held_old == held_new}")
if held_old != held_new:
    print("  only old:", sorted(set(held_old) - set(held_new)), " only new:", sorted(set(held_new) - set(held_old)))
ch, hd = house_and_dynasty(new)
house = ch.get(p_new)
dyn = hd.get(house)
line = {c for c, h in ch.items() if h == house or hd.get(h) == dyn}
new_keys = {k: h for k, h in t_new.items() if k not in t_old}
by_line = sorted(k for k, h in new_keys.items() if h in line)
print(f"titles the old save lacks: {len(new_keys)} ({sum(1 for h in new_keys.values() if h)} held); "
      f"player's house {house}, dynasty {dyn}, {len(line)} living members")
print(f"new-map titles held by the player's house or dynasty: {len(by_line)}", by_line[:30])
