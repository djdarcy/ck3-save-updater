"""S1 (patch-day goal): gamediff recounted by key across folders.

`ck3update gamediff` groups definitions by parent folder, so 1.21's move of buildings into subfolders reads as
"908 removed" (consultant, round 1, finding 5). This counts per kind across the whole folder tree instead: buildings
(common/buildings, recursive), titles (every e_/k_/d_/c_/b_ block of common/landed_titles), modifiers
(common/modifiers, recursive), and the removed keys a save still names.
Known answer: castle_01 exists in both versions (moved, not removed).
Run: python -I -X utf8 tests/one-offs/thinking/gamediff_by_key_1_21.py <old game dir> <new game dir> <save.ck3>
"""
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
from ck3_save_migrator.savefile import read_save  # noqa: E402

TOP = re.compile(r"(?m)^([A-Za-z][A-Za-z0-9_\-]*)\s*=\s*\{")
TITLE = re.compile(r"(?m)^\s*([ekdcb]_[A-Za-z0-9_\-]+)\s*=\s*\{")


def keys(folder, pat=TOP):
    return {m.group(1) for f in pathlib.Path(folder).rglob("*.txt")
            for m in pat.finditer(f.read_text("utf-8-sig", "replace"))}


def main(old, new, save):
    g = read_save(save).gamestate
    print(f"known answer: castle_01 in old {('castle_01' in keys(pathlib.Path(old) / 'common/buildings'))}, "
          f"new {('castle_01' in keys(pathlib.Path(new) / 'common/buildings'))} (expect True, True)")
    for kind, sub, pat in (("buildings", "common/buildings", TOP), ("titles", "common/landed_titles", TITLE),
                           ("modifiers", "common/modifiers", TOP)):
        o, n = keys(pathlib.Path(old) / sub, pat), keys(pathlib.Path(new) / sub, pat)
        removed = sorted(o - n)
        used = [k for k in removed if re.search(rb'[="\s]' + re.escape(k.encode()) + rb'["\s}]', g)]
        print(f"\n{kind}: old {len(o)}, new {len(n)}; removed {len(removed)}, added {len(n - o)}; "
              f"removed and named in the save: {len(used)}")
        print("  named:", used[:40], "..." if len(used) > 40 else "")


if __name__ == "__main__":
    main(*sys.argv[1:4])
