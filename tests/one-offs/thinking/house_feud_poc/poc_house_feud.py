"""PoC: 1.8's house-feud story becomes a 1.20 house relation at the feud level.

1.8 (bp1) ran each house feud as a story (story_cycle="story_cycle_house_feud", owner = a character, variable
house_feud_house = the rival house). 1.20 comments that story cycle out and tracks feuds as house relations
(common/house_relation_types/00_house_relations.txt, level feud: -30 opinion, eradicate CB, hostile schemes). A 1.20
save holds them in house_relations={ database={ <id>={ houses={ a b } type=default_house_relation
level=default_house_relation_level_<level> fraction=<score> history={...} } } }. Our updated save has no such
section (1.8 had none; 1.20 creates it on load).

Prediction (2026-11-04, before running): with the section added holding the founding save's two feuds (Jutta's house
4316 vs 1633; Ngodup's house 3981 vs 3974), the game's day-one re-save keeps both relations at
default_house_relation_level_feud, and error.log has no line naming house_relation.
Control (built to fail): a third entry with level=default_house_relation_level_bogus, a level 1.20 does not define;
predicted dropped or rewritten by the re-save, or logged. If it survives as written, the method cannot see a rejection
and no result counts.
Fallback: the feuds stay listed as lost (EXCLUSIONS).

Usage: python -I poc_house_feud.py <in.ck3> <out.ck3>"""
import sys

sys.path.insert(0, r"C:\code\ck3-save-migrator")
from ck3_save_migrator import savefile as sf  # noqa: E402

ENTRIES = [  # (id, house a, house b, level) -- houses from the stories' owners and house_feud_house variables
    (0, 4316, 1633, "feud"),
    (1, 3981, 3974, "feud"),
    (2, 4316, 3981, "bogus"),   # the control
]
save = sf.read_save(sys.argv[1])
d = save.gamestate
assert b"\nhouse_relations={" not in d, "the input already has house_relations"
block = b"house_relations={\n\tdatabase={\n" + b"".join(
    f"\t\t{i}={{\n\t\t\thouses={{ {a} {b} }}\n\t\t\ttype=default_house_relation\n"
    f"\t\t\tlevel=default_house_relation_level_{lvl}\n\t\t\tfraction=0\n\t\t}}\n".encode() for i, a, b, lvl in ENTRIES
) + b"\t}\n}\n"
save.replace_range(len(d), len(d), (b"" if d.endswith(b"\n") else b"\n") + block)   # appended at the top level
sf.write_save(save, sys.argv[2])
back = sf.read_save(sys.argv[2]).gamestate
print("written; house_relations entries in the output:", back.count(b"type=default_house_relation"))
