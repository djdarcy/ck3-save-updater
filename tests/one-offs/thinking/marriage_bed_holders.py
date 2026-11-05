"""S4: who holds rejected_from_marriage_bed_modifier in a save -- alive or dead, and their spouses.
1.20 replaced the character modifier with the pair relation wedding_very_bad_fertility (fertility -1.4), so only a
living holder with a living spouse has anything to carry. Usage: marriage_bed_holders.py <save>"""
import re
import sys

sys.path.insert(0, r"C:\code\ck3-save-migrator")
from ck3_save_migrator import savefile as sf  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
d = sf.read_save(sys.argv[1]).gamestate


def section(name):
    m = re.search(rb"(?m)^" + name + rb"=\{", d)
    depth, i = 0, m.end() - 1
    while True:
        c = d[i]
        if c == 0x7B:
            depth += 1
        elif c == 0x7D:
            depth -= 1
            if depth == 0:
                return m.start(), i
        i += 1


def entries(lo, hi):
    """id -> (start, end) of each entry `N={` at column 0 inside a section (the character sections' layout)."""
    out = {}
    for m in re.finditer(rb"(?m)^(\d+)=\{", d[lo:hi]):
        out[int(m.group(1))] = lo + m.start()
    ids = sorted(out, key=out.get)
    return {k: (out[k], out[ids[j + 1]] if j + 1 < len(ids) else hi) for j, k in enumerate(ids)}


living = entries(*section(rb"living"))
dead = entries(*section(rb"dead_unprunable"))
alive_n = dead_n = 0
for cid, (a, b) in sorted(living.items()):
    body = d[a:b]
    if b"rejected_from_marriage_bed_modifier" not in body:
        continue
    alive_n += 1
    spouses = re.findall(rb"(?:spouse|primary_spouse)=(\d+)", body) + \
        sum([re.findall(rb"\d+", s) for s in re.findall(rb"spouse=\{([^}]*)\}", body)], [])
    sp = sorted({int(s) for s in spouses})
    state = [f"{s}:{'alive' if s in living else 'dead' if s in dead else '?'}" for s in sp]
    print(f"alive {cid} spouses {state}")
for cid, (a, b) in dead.items():
    if b"rejected_from_marriage_bed_modifier" in d[a:b]:
        dead_n += 1
print(f"holders alive {alive_n}, dead {dead_n}")
