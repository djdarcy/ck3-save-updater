"""S3 measure 3 (after-goal-pass goal): does a culture's head_determination follow from its culture_template?

For every culture in each save given: its culture_template, the head_determination that template's definition declares
in game/common/culture/cultures/*.txt (or "undeclared"), and the save's own value. Prints, per save, how many agree,
and the value the game writes where the definition declares none.
Run: python -I -X utf8 tests/one-offs/head_determination_measure.py <game dir> <save> [<save> ...]
"""
import collections
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from after_goal_rows_measure import table          # noqa: E402
from ck3_save_migrator.savefile import read_save   # noqa: E402


def definitions(game):
    """template key -> declared head_determination (None when the block declares none)."""
    out = {}
    for f in sorted((pathlib.Path(game) / "common" / "culture" / "cultures").glob("*.txt")):
        text = f.read_text(encoding="utf-8-sig", errors="replace")
        for m in re.finditer(r"(?m)^([a-z][a-z0-9_]*)\s*=\s*\{", text):
            depth, i = 0, m.end() - 1
            while i < len(text):
                depth += {"{": 1, "}": -1}.get(text[i], 0)
                if depth == 0:
                    break
                i += 1
            hd = re.search(r"(?m)^\thead_determination\s*=\s*(\w+)", text[m.end():i])
            out[m.group(1)] = hd.group(1) if hd else None
    return out


def main(game, saves):
    defs = definitions(game)
    print(f"{len(defs)} culture definitions; declared: {collections.Counter(defs.values())}")
    for s in saves:
        t = table(read_save(s).gamestate, "culture_manager/cultures")
        agree, disagree, undeclared, no_template = 0, [], collections.Counter(), collections.Counter()
        for cid, f in t.items():
            tmpl = (f.get("culture_template") or b"").strip(b'"').decode()
            have = (f.get("head_determination") or b"").strip(b'"').decode() or None
            if not tmpl:
                no_template[have] += 1
                continue
            want = defs.get(tmpl, "?no-definition")
            if want is None:
                undeclared[have] += 1
            elif want == have:
                agree += 1
            else:
                disagree.append((cid, tmpl, want, have))
        print(f"{pathlib.Path(s).name}: {len(t)} cultures; template declares and agrees {agree}, "
              f"disagrees {len(disagree)} {disagree[:4]}; template undeclared -> {dict(undeclared)}; "
              f"no template -> {dict(no_template)}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
