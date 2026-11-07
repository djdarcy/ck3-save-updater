"""Do a save's faces fit the source layout R19 builds with NEITHER --old-portrait-mods NOR --old-game-dir (the
built-in tables)? R19's own setup and fit check, read only, for saves `status` will not plan (older than 1.8).
For the gene-table goal (S1). Usage: python -I faces_fit.py <game dir> <portrait mods ids,comma> <save.ck3> ..."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from ck3_save_migrator import dna, savefile as sf

game, mods = Path(sys.argv[1]), sys.argv[2].split(",")
for p in sys.argv[3:]:
    s = sf.read_save(p)
    st = dna.setup(save_meta=s.meta, game_dir=game, portrait_mods_given=mods, gamestate=lambda: s.gamestate)
    res = dna.plan_save(s.gamestate, st)
    bad = sum(res.impossible.values())
    print(f"== {Path(p).name}  ({dna.save_versions(s.meta)['version'] if hasattr(dna, 'save_versions') else ''})")
    print(f"   source: {st.source.name}")
    for m, f in st.source_mods:
        print(f"   {m}: {f[:150]}")
    if st.source_choice:
        print(f"   choice: {st.source_choice[:200]}")
    print(f"   faces {sum(res.lengths.values()):,}; undefined template values {bad:,} of {res.template_bytes:,}; "
          f"wrong layout: {res.wrong_layout}; by gene {res.impossible_by_gene()[:3]}")
