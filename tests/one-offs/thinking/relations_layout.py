"""S4 /measure: how a 1.20 save stores a scripted relation (for the marriage-bed successor wedding_very_bad_fertility).
Per save: the relations section's head, how many entries carry scripted_relations, and for a corresponding relation
(potential_friend) whether a pair is stored once or in both directions. Usage: relations_layout.py <save> [...]"""
import re
import sys
from collections import Counter

sys.path.insert(0, r"C:\code\ck3-save-migrator")
from ck3_save_migrator import savefile as sf  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
for path in sys.argv[1:]:
    raw = open(path, "rb").read()
    try:
        d = sf.parse_save(raw).gamestate
    except Exception:
        d = raw
    m = re.search(rb"(?m)^relations=\{", d)
    end = re.search(rb"(?m)^\}", d[m.end():]).start() + m.end()
    sec = d[m.start():end]
    print(f"== {path}: relations section {len(sec):,} bytes")
    print(sec[:300].decode("utf-8", "replace"))
    ents = re.split(rb"\n\t\}\n \{|\n\t\{", sec)
    pairs, names = set(), Counter()
    for e in re.finditer(rb"owner=(\d+)\s+target=(\d+)(.*?)(?=owner=|\Z)", sec, re.S):
        a, b, body = e.group(1), e.group(2), e.group(3)
        for s in re.finditer(rb"scripted_relations=\{(.*?)\n\t\t\t\}", body, re.S):
            for n in re.findall(rb"(\w+)=\{", s.group(1)):
                names[n.decode()] += 1
                if n == b"potential_friend":
                    pairs.add((a, b))
    both = sum(1 for a, b in pairs if (b, a) in pairs)
    print(f"scripted relation names: {names.most_common(12)}")
    print(f"potential_friend pairs {len(pairs)}, stored both ways {both}")
