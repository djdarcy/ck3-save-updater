"""patch_registry_proof: does the founding campaign migrate to the same gamestate through the shipped patch pack as
through the Python rule registry? (epic #14, goal slice 2, AC-F1 of the patch-contract design; 2026-10-28)

Runs `migrate` through cli.main in-process, with the same flags as the play6 build, three times:
  python-a   the registry as shipped (the Python rules)
  python-b   the same again: the control. If a and b differ, migrate is not deterministic and the comparison below
             means nothing until that is understood (it also answers half of slice 4's determinism question)
  pack       REGISTRY's contents replaced in place by rules_from_pack() (so select() and every importer see it)
Then prints the sha256 of each output's gamestate and, when pack differs from python-a, the first differing offset
with 300 bytes of context from each side.

Usage: python -I tests/one-offs/patch_registry_proof.py <original.ck3> <reference.ck3> <game dir> <old game dir> <out dir>
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ck3_save_migrator import cli  # noqa: E402
from ck3_save_migrator import rules as R  # noqa: E402
from ck3_save_migrator.patches.pack import rules_from_pack  # noqa: E402
from ck3_save_migrator.savefile import read_save  # noqa: E402


def migrate(src, ref, game, old_game, out):
    argv = ["migrate", src, "--rules", "all,R14,R15,R16", "--reference", ref, "--game-dir", game,
            "--old-game-dir", old_game, "--wos-shape", "faith", "-o", str(out), "--force"]
    rc = cli.main(argv)
    if rc not in (0, None):
        raise SystemExit(f"migrate exited {rc} for {out}")


def gs_sha(p: Path) -> tuple[str, bytes]:
    g = read_save(p).gamestate
    return hashlib.sha256(g).hexdigest(), g


def main():
    src, ref, game, old_game, out_dir = sys.argv[1:6]
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    python_order = [r.id for r in R.REGISTRY]
    migrate(src, ref, game, old_game, out / "proof_python_a.ck3")
    migrate(src, ref, game, old_game, out / "proof_python_b.ck3")
    pack = rules_from_pack()
    assert [r.id for r in pack] == python_order, ("pack order differs", [r.id for r in pack], python_order)
    saved = list(R.REGISTRY)
    R.REGISTRY[:] = pack
    try:
        migrate(src, ref, game, old_game, out / "proof_pack.ck3")
    finally:
        R.REGISTRY[:] = saved
    hashes = {}
    for name in ("python_a", "python_b", "pack"):
        hashes[name] = gs_sha(out / f"proof_{name}.ck3")
        print(f"{name:9} {hashes[name][0]}  {len(hashes[name][1]):,} bytes")
    print("control (python a == b):", hashes["python_a"][0] == hashes["python_b"][0])
    same = hashes["pack"][0] == hashes["python_a"][0]
    print("AC-F1 (pack == python):  ", same)
    if not same:
        a, b = hashes["python_a"][1], hashes["pack"][1]
        i = next((k for k in range(min(len(a), len(b))) if a[k] != b[k]), min(len(a), len(b)))
        print(f"first difference at byte {i:,}")
        print("python:", a[max(0, i - 200):i + 100].decode(errors="replace"))
        print("pack:  ", b[max(0, i - 200):i + 100].decode(errors="replace"))


if __name__ == "__main__":
    main()
