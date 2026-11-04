"""Check that an R25 build differs from play8 only by R25's renames: same line count, and every differing line
becomes play8's once the successors are put back. Usage: r25_vs_play8.py <play8.ck3> <r25.ck3>"""
import re, sys
from collections import Counter
sys.path.insert(0, r"C:\code\ck3-save-migrator")
from ck3_save_migrator import savefile as sf
a = sf.read_save(sys.argv[1]).gamestate.split(b"\n")
b = sf.read_save(sys.argv[2]).gamestate.split(b"\n")
print("lines", len(a), len(b))
back = [(rb"erudite_perk", b"scholar_perk"), (rb'type="order_serjeants"', b'type="teutonic_knights"'),
        (rb"artifact_([a-z_]+)_scheme_phase_duration_add_(\d+)_modifier", rb"artifact_\1_scheme_power_add_\2_modifier")]
diff, explained, kinds = 0, 0, Counter()
for x, y in zip(a, b):
    if x == y:
        continue
    diff += 1
    z = y
    for pat, rep in back:
        z = re.sub(pat, rep, z)
    if z == x:
        explained += 1
        kinds[(b"perk" if b"perk={" in y else b"type" if b"type=" in y else b"modifiers").decode()] += 1
    else:
        print("UNEXPLAINED:", x[:160], "|", y[:160])
print("differing lines", diff, "explained by R25", explained, dict(kinds))
