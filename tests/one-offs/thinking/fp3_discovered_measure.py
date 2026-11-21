"""Does a fresh game start any culture with the prefixed (fp3_) innovations discovered? If so, R47's evidence path
skipped them, because innovation_eras keeps only keys starting innovation_. Also: is every innovation key listed on
EVERY reference culture (G1: the union and the intersection agree)?

Goal 2026-11-20__16-02-08 S2. Usage: python -I tests/one-offs/thinking/fp3_discovered_measure.py <ref.ck3> [...]
"""
import collections
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from ck3_save_migrator.carry_1_21 import _cultures  # noqa: E402
from ck3_save_migrator.savefile import read_save  # noqa: E402

for p in sys.argv[1:]:
    g = read_save(p).gamestate
    cults = [(e.key.decode(), t, era, inn) for e, t, era, inn, span in _cultures(g) if span is not None]
    union = set().union(*(inn for *_, inn in cults))
    inter = set.intersection(*(set(inn) for *_, inn in cults))
    disc = collections.Counter(i for *_, inn in cults for i, pr in inn.items() if i.startswith("fp3_") and (pr or 0) >= 100)
    tmpl = sorted({t for _, t, _, inn in cults for i, pr in inn.items() if not i.startswith("innovation_") and (pr or 0) >= 100})
    print(f"{Path(p).name}: {len(cults)} cultures with a list; union {len(union)}, intersection {len(inter)}, "
          f"partial {sorted(union - inter)}")
    print(f"  prefixed keys discovered: {dict(disc) or 'none'}; on templates {tmpl or '-'}")
