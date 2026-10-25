"""Acceptance checks for the transplant (design A11). This first part: A11.3, barony coverage.

--baronies: for an output save, against the 1.20 game's own landed_titles and the original 1.8.1 save:
  * every barony key 1.20 defines appears in the output exactly once (missing ones listed);
  * no barony key appears twice;
  * output baronies 1.20 does not define (the dead titles R15 maps; the design names b_nanhu and b_wuda as the
    two wastelands that stay without a successor);
  * every barony of the original save is accounted for: kept under its key (identity), or renamed by R15 (the
    report's rename table, when given), or unmapped.
Prints `unmapped: N` last, as the acceptance line.

Usage: python -I tests/one-offs/check_a11.py <output.ck3> --baronies --original <1.8.1 save.ck3>
                                             --game-dir <1.20 game dir> [--renames <report.json>]
"""
import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ck3_save_migrator import savefile as sf  # noqa: E402
from ck3_save_migrator import translate as T  # noqa: E402

TITLE = re.compile(r"\b(b_[\w\-']+)\s*=\s*\{")


def defined_baronies(game: Path) -> set[str]:
    out = set()
    for f in (game / "common" / "landed_titles").glob("*.txt"):
        out |= set(TITLE.findall(re.sub(r"#[^\n]*", "", f.read_text(encoding="utf-8-sig", errors="replace"))))
    return out


def save_baronies(g: bytes) -> Counter:
    c = Counter()
    for _, e in T.entries(g, "landed_titles/landed_titles"):
        k = T._depth0(g, e, T._KEY)
        if k and k.startswith(b"b_"):
            c[k.decode()] += 1
    return c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--baronies", action="store_true")
    ap.add_argument("--original", required=True)
    ap.add_argument("--game-dir", required=True)
    ap.add_argument("--renames", help="a migrate report whose R15 extra has a 'renamed' {old: new} table")
    a = ap.parse_args()
    defined = defined_baronies(Path(a.game_dir))
    out = save_baronies(sf.read_save(a.out).gamestate)
    orig = save_baronies(sf.read_save(a.original).gamestate)
    renames = {}
    if a.renames:
        for r in json.loads(Path(a.renames).read_text(encoding="utf-8")).get("rules", []):
            renames.update(r.get("extra", {}).get("renamed", {}))
    dup = sorted(k for k, n in out.items() if n > 1)
    missing = sorted(defined - set(out))
    undefined = sorted(k for k in out if k not in defined)
    kept = sum(1 for k in orig if k in out and k in defined)
    renamed = {k: renames[k] for k in orig if k in renames and renames[k] in defined}
    unmapped = sorted(k for k in orig if not (k in defined and k in out) and k not in renamed)
    print(f"1.20 defines {len(defined):,} baronies; the output has {sum(out.values()):,} barony entries, "
          f"{len(out):,} keys")
    print(f"  missing from the output: {len(missing)} {missing[:10]}")
    print(f"  duplicated in the output: {len(dup)} {dup[:10]}")
    print(f"  in the output but not defined by 1.20: {len(undefined)} {undefined[:12]}")
    print(f"original save baronies {len(orig):,}: kept by key {kept:,}, renamed {len(renamed)}, unmapped {len(unmapped)}")
    print(f"  unmapped: {unmapped[:70]}")
    print(f"unmapped: {len(unmapped)}")


if __name__ == "__main__":
    main()
