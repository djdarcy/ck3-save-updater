"""INV-6 (template cultures registered) on real saves: the count lint's check_registries reports for each.
Expected 2026-10-26: vanilla reference 0, the pre-(c) output e2e_1b 55, the (c) output e2e_1c 0. Run with python -I."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ck3_save_migrator import lint, savefile as sf  # noqa: E402

for p in sys.argv[1:]:
    g = sf.read_save(p).gamestate
    rep = lint.LintReport()
    lint.check_registries(g, rep)
    for f in rep.findings if hasattr(rep, "findings") else rep.items:
        print(Path(p).name, f)
