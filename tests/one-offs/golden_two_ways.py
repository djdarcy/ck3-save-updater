"""golden_two_ways: is the played save built the same twice, and the same through run patches? (epic #14, goal
slice 4, AC-G1 of the patch-contract design; 2026-10-28)

djdarcy, 2026-10-27 14:46: "all our old tools we use to build our save can still be used exactly as they are with
our pypi tool as another method to guarantee we get our goldens". The golden here is play6's played save, built by
migrate, then dna_whole_save.py (faces from the 967 witness), then playset_rules.py (the "Claude" playset). The
migrate step's determinism is already measured (patch_registry_proof.py: three identical gamestates).

Steps:
  A  the scripts by hand, again, on the migrate output (dna_whole_save.py, then playset_rules.py, unchanged)
  B  migrate the original with --pack <recipe> --vars <vars.toml> --allow-run: the same two scripts as run patches
Compares A, B and the existing golden by gamestate sha256 and by the meta block's sha256 (the zip itself carries
member timestamps, so the .ck3 bytes are not the measure). Known answer: A against the golden is the determinism
check; if it fails, B is not judged.

Usage: python -I tests/one-offs/golden_two_ways.py <original.ck3> <migrated.ck3> <golden played.ck3> <recipe dir> <out dir>
       (game, reference and old game folders are the founding campaign's, written below)
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from ck3_save_migrator.savefile import read_save  # noqa: E402

GAME = "E:/SteamLibrary/steamapps/common/Crusader Kings III/game"
REF = str(ROOT / "private/data/originals/reference-1.20/ref_1_20_987_10_27.ck3")
OLD_GAME = str(ROOT / "private/data/versions/1.8.2/game")


def digest(p: Path) -> tuple[str, str]:
    s = read_save(p)
    return hashlib.sha256(s.gamestate).hexdigest(), hashlib.sha256(bytes(s.meta or b"")).hexdigest()


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    tail = (r.stdout + r.stderr).strip().splitlines()[-2:]
    print(f"  rc={r.returncode}  {' | '.join(tail)[:300]}")
    if r.returncode != 0:
        raise SystemExit(f"step failed: {cmd[:4]}")


def main():
    original, migrated, golden, recipe, out = sys.argv[1:6]
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    v = tomllib.loads(Path(recipe, "vars.toml").read_text(encoding="utf-8"))
    py = sys.executable
    print("A: the scripts by hand")
    run([py, "-I", str(ROOT / "tests/one-offs/dna_whole_save.py"), migrated, v["witness"], str(out / "a_faces.ck3")])
    run([py, "-I", str(ROOT / "tests/one-offs/playset_rules.py"), str(out / "a_faces.ck3"), str(out / "a_play.ck3"),
         GAME, *v["pairs"]])
    print("B: migrate with the recipe pack")
    run([py, "-m", "ck3_save_migrator", "migrate", original, "--rules", "all,R14,R15,R16", "--reference", REF,
         "--game-dir", GAME, "--old-game-dir", OLD_GAME, "--wos-shape", "faith", "--pack", recipe,
         "--vars", str(Path(recipe, "vars.toml")), "--allow-run", "-o", str(out / "b_play.ck3"), "--force"])
    g, a, b = digest(Path(golden)), digest(out / "a_play.ck3"), digest(out / "b_play.ck3")
    for name, d in (("golden", g), ("A by hand", a), ("B recipe", b)):
        print(f"{name:10} gamestate {d[0][:16]}  meta {d[1][:16]}")
    print("determinism (A == golden):", a == g)
    print("AC-G1 (B == golden):       ", b == g)


if __name__ == "__main__":
    main()
