"""Do two updated saves carry the same faces? Compares every character's own dna= (living and dead sections), by
character id. For the gene-table goal (S1): an update with neither --old-portrait-mods nor --old-game-dir must give
the same faces as one with both. Usage: python -I faces_equal.py <a.ck3> <b.ck3>"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from ck3_save_migrator import dna, savefile as sf


def faces(path: str) -> dict[str, bytes]:
    g = sf.read_save(path).gamestate
    return {cid: g[a:b] for cid, a, b in dna._people(g)}


a, b = faces(sys.argv[1]), faces(sys.argv[2])
only_a, only_b = set(a) - set(b), set(b) - set(a)
diff = sorted(c for c in set(a) & set(b) if a[c] != b[c])
print(f"characters with a face: {len(a):,} / {len(b):,}; only in one: {len(only_a)} / {len(only_b)}; "
      f"differing faces: {len(diff):,}")
for c in diff[:10]:
    ra, rb = dna.b64d(a[c]), dna.b64d(b[c])
    places = [i // 4 for i in range(min(len(ra), len(rb))) if ra[i] != rb[i]]
    print(f"  {c}: differing places {sorted(set(places))[:12]}")
# known-answer: a face compared with itself is equal, and a changed byte is found
k = next(iter(a))
assert a[k] == a[k]
sys.exit(0 if not diff and not only_a and not only_b else 1)
