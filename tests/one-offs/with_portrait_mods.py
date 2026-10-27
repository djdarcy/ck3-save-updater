"""with_portrait_mods: run one command with CFP, EPE and the CFP+EPE patch enabled in CK3's dlc_load.json, then
restore the file byte-exact, whatever the command did.

Layout (c), the faces' target, needs those three mods loaded (djdarcy's 2026-10-25 21:11 ruling allows enabling
them for a run under a verified backup). The backup goes to private/data/backups/<stamp>__dlc_load-before-<tag>/
with its sha256; the restore is checked against it and the script fails loudly if it does not match.

--also <folder>: also load the mod in <folder> (holding its own descriptor.mod) for this run, by writing a
`MIGRATE_TEST__<folder name>.mod` descriptor (path= the folder) into the game's mod folder for the run and moving
it to the recoverable trash with `dz safedel` afterwards. Repeatable; loaded after the three portrait mods.

--mod <mod/ugc_N.mod>: also enable an installed mod by its descriptor (2026-10-27: the first-play playset's load
test). Repeatable; loaded after the three portrait mods, in the order given.

Usage: python -I tests/one-offs/with_portrait_mods.py <tag> [--mod <descriptor> ...] [--also <folder> ...] -- <command ...>
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
DLC = Path.home() / "Documents" / "Paradox Interactive" / "Crusader Kings III" / "dlc_load.json"
MODS = ["mod/ugc_2220098919.mod", "mod/ugc_2507209632.mod", "mod/ugc_2996881191.mod"]   # CFP, EPE, patch


def main() -> int:
    tag = sys.argv[1]
    cut = sys.argv.index("--")
    cmd = sys.argv[cut + 1:]
    also = [Path(sys.argv[i + 1]).resolve() for i in range(2, cut) if sys.argv[i] == "--also"]
    # --mod <mod/ugc_N.mod>: also enable an installed mod by its descriptor, after the portrait mods, in order
    extra = [sys.argv[i + 1] for i in range(2, cut) if sys.argv[i] == "--mod"]
    for m in extra:
        if not (DLC.parent / m).exists():
            raise SystemExit(f"{m}: no such descriptor in {DLC.parent / 'mod'}")
    descriptors = []
    for folder in also:
        text = (folder / "descriptor.mod").read_text(encoding="utf-8")
        d = DLC.parent / "mod" / f"MIGRATE_TEST__{folder.name}.mod"
        if d.exists():
            raise SystemExit(f"{d} already exists; not overwriting it")
        d.write_text(text.rstrip() + f'\npath="{folder.as_posix()}"\n', encoding="utf-8")
        descriptors.append(d)
    original = DLC.read_bytes()
    sha = hashlib.sha256(original).hexdigest()
    bdir = PROJECT / "private" / "data" / "backups" / f"{time.strftime('%Y-%m-%d__%H-%M-%S')}__dlc_load-before-{tag}"
    bdir.mkdir(parents=True)
    (bdir / "dlc_load.json").write_bytes(original)
    (bdir / "sha256.txt").write_text(f"{sha}  dlc_load.json\n", encoding="utf-8")
    if hashlib.sha256((bdir / "dlc_load.json").read_bytes()).hexdigest() != sha:
        raise SystemExit("backup did not verify; nothing changed")
    cfg = json.loads(original)
    cfg["enabled_mods"] = MODS + extra + [f"mod/{d.name}" for d in descriptors]
    DLC.write_text(json.dumps(cfg), encoding="utf-8")
    print(f"[mods] enabled {cfg['enabled_mods']}; backup {bdir}")
    try:
        rc = subprocess.call(cmd)
    finally:
        for d in descriptors:
            subprocess.call(["dz", "safedel", "--yes", str(d)])     # without --yes it prompts, and aborts unattended
            print(f"[mods] {d.name} moved to the recoverable trash: {'yes' if not d.exists() else 'NO, still there'}")
        DLC.write_bytes(original)
        ok = hashlib.sha256(DLC.read_bytes()).hexdigest() == sha
        print(f"[mods] dlc_load.json restored: {'sha OK' if ok else 'SHA MISMATCH'}")
        if not ok:
            raise SystemExit(f"dlc_load.json restore failed; the backup is in {bdir}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
