"""stage_040_game_checks: the two saves for the 0.4.0 checklist's in-game steps, written as new MIGRATE_TEST__ saves.

- 4.2a: the sample pack's X1 (the load-screen name) applied to a 1.20 vanilla save, so the load screen shows
  "Edited with ck3update". Made with the tool's own pack loader and apply_patch, from the shipped example text.
- 4b.1: an R19 unmodded update (the 1.8.1 vanilla-layout fixture through update, faces carried into vanilla 1.20),
  copied as it is.

Both load with no mods. Writes only the two named outputs; refuses to overwrite.

Usage: python -I tests/one-offs/stage_040_game_checks.py <1.20 vanilla save> <r19 vanilla output> <save folder>
"""
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ck3_save_migrator import savefile as sf  # noqa: E402
from ck3_save_migrator import userpacks as U  # noqa: E402
from ck3_save_migrator.patches import apply_patch, read_pack  # noqa: E402


def main():
    base, r19, folder = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    out_a, out_b = folder / "MIGRATE_TEST__040_example.ck3", folder / "MIGRATE_TEST__040_faces.ck3"
    for o in (out_a, out_b):
        if o.exists():
            raise SystemExit(f"refusing to overwrite {o}")
    with tempfile.TemporaryDirectory() as t:
        pack_dir = Path(t) / "example"
        for rel, text in U.EXAMPLE.items():
            p = pack_dir / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
        x1 = read_pack(pack_dir).patches["X1"]
        save = sf.read_save(base)
        res = apply_patch(save, x1, {})
        sf.write_save(save, out_a)
    print(f"4.2a: {out_a} ({res})")
    shutil.copy2(r19, out_b)
    print(f"4b.1: {out_b} (copy of {r19.name})")


if __name__ == "__main__":
    main()
