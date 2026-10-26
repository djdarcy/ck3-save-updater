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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from shape_diff import load as _load_any  # noqa: E402  (also reads the game's plain-text re-saves)

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


def holders(a) -> None:
    """A11.1 and A11.2: who holds the titles the transplant added.

    A11.1: no title that is new to the save (absent from the migrated input, not a clean R15 rename) is held by
    a campaign character (one the input already had), and none by the player.
    A11.2: every such title the reference holds is held in the output by the reference's holder, translated.
    """
    inp = _load_any(a.input)
    out = _load_any(a.out)          # our output, or the game's re-save of it (A11 re-checked after the load)
    ref = _load_any(a.reference)
    tr = T.Translator.build(inp, ref)
    cm = tr.spaces["character"]
    campaign = T.space_ids(inp, "character")
    in_keys = set(T.keyed(inp, "landed_titles/landed_titles"))
    renamed_to = set()
    if a.renames:
        for r in json.loads(Path(a.renames).read_text(encoding="utf-8")).get("rules", []):
            renamed_to |= {v.encode() for v in r.get("extra", {}).get("renamed", {}).values()}

    def holder_map(g):
        out = {}
        for _, e in T.entries(g, "landed_titles/landed_titles"):
            k = T._depth0(g, e, T._KEY)
            m = re.search(rb"\n\tholder=(\d+)", g[e.open:min(e.close, e.open + 4096)])
            out[k] = int(m.group(1)) if m else None
        return out

    oh, rh = holder_map(out), holder_map(ref)
    new = [k for k in oh if k not in in_keys and k not in renamed_to]
    player = int(re.search(rb"currently_played_characters=\{\s*(\d+)", inp).group(1))
    by_campaign = [(k.decode(), oh[k]) for k in new if oh[k] is not None and oh[k] in campaign]
    by_player = [k.decode() for k in new if oh[k] == player]
    mismatch, missing = [], []
    for k in new:
        r = rh.get(k)
        if r is None:
            continue
        want = cm.translate(r)
        if oh[k] is None:
            missing.append(k.decode())
        elif oh[k] != want:
            mismatch.append((k.decode(), oh[k], want))
    print(f"titles new to the save: {len(new):,}; held in the output {sum(1 for k in new if oh[k] is not None):,}")
    print(f"A11.1 player ({player}) holds new: {len(by_player)} {by_player[:10]}")
    print(f"A11.1 campaign characters hold new: {len(by_campaign)} {by_campaign[:10]}")
    if a.named:                         # step 1c: the transplant report's named cases are not mismatches
        named, settled = set(), set()
        for r in json.loads(Path(a.named).read_text(encoding="utf-8")).get("rules", []):
            named |= {x["barony"] for x in r.get("extra", {}).get("reparent_left", [])}
            settled |= {x["new county"] for x in r.get("extra", {}).get("settled", [])}
        # step 1c-bis: a settled county, and a barony of it (its carried capital), goes to the campaign by rule
        ref_dj = {}
        for _, e in T.entries(ref, "landed_titles/landed_titles"):
            m = re.search(rb"\n\tde_jure_liege=(\d+)", ref[e.open:min(e.close, e.open + 4096)])
            ref_dj[T._depth0(ref, e, T._KEY)] = int(m.group(1)) if m else None
        ref_key = {i: T._depth0(ref, e, T._KEY) for i, e in T.entries(ref, "landed_titles/landed_titles")}
        settled_b = {s.encode() for s in settled}
        for k in list(oh):
            if k in settled_b or ref_key.get(ref_dj.get(k)) in settled_b:
                named.add(k.decode())
        print(f"A11 settled by 1c-bis (counties {len(settled)}), counted as named")
        inherit = sorted(k for k, _ in by_campaign if k in named)
        by_campaign = [(k, h) for k, h in by_campaign if k not in named]
        print(f"A11.1 campaign characters hold new, by the report's rules: {len(inherit)}; NOT named: "
              f"{len(by_campaign)} {by_campaign[:10]}")
        print(f"A11.2 named in the report (reparent_left), not counted: "
              f"{sorted(k for k, *_ in mismatch if k in named) + sorted(k for k in missing if k in named)}")
        mismatch = [m for m in mismatch if m[0] not in named]
        missing = [k for k in missing if k not in named]
    print(f"A11.2 reference-held new titles unheld in the output: {len(missing)} {missing[:10]}")
    print(f"A11.2 held by someone else than the reference's holder: {len(mismatch)} {mismatch[:10]}")
    print(f"player_holds_new: {len(by_player)}  ref_held_mismatch: {len(mismatch) + len(missing)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--baronies", action="store_true")
    ap.add_argument("--holders", action="store_true")
    ap.add_argument("--original")
    ap.add_argument("--input", help="the migrated save the transplant ran on (for --holders)")
    ap.add_argument("--reference", help="the 1.20 reference save (for --holders)")
    ap.add_argument("--named", help="the transplant's report.json: its named 1c cases are not counted (--holders)")
    ap.add_argument("--game-dir")
    ap.add_argument("--renames", help="a migrate report with R15's table")
    a = ap.parse_args()
    if a.holders:
        return holders(a)
    defined = defined_baronies(Path(a.game_dir))
    out = save_baronies(sf.read_save(a.out).gamestate)
    orig = save_baronies(sf.read_save(a.original).gamestate)
    table = {}
    if a.renames:
        for r in json.loads(Path(a.renames).read_text(encoding="utf-8")).get("rules", []):
            if r.get("id") != "R15":                 # other rules may report a "table" of their own
                continue
            for row in r.get("extra", {}).get("table", []):
                table[row["key"]] = row
    dup = sorted(k for k, n in out.items() if n > 1)
    missing = sorted(defined - set(out))
    undefined = sorted(k for k in out if k not in defined)
    renamed, successor, wasteland, kept, unmapped = {}, {}, [], 0, []
    for k in orig:
        row = table.get(k)
        if row and row["class"] == "clean" and row["successors"][0] in out:
            renamed[k] = row["successors"][0]
        elif row and row["class"] == "wasteland":
            wasteland.append(k)
        elif row and row["successors"] and all(s in out for s in row["successors"]):
            successor[k] = row["successors"]                 # removed; its land's 1.20 baronies came from the reference
        elif k in defined and k in out:
            kept += 1
        else:
            unmapped.append(k)
    print(f"1.20 defines {len(defined):,} baronies; the output has {sum(out.values()):,} barony entries, "
          f"{len(out):,} keys")
    print(f"  missing from the output: {len(missing)} {missing[:10]}")
    print(f"  duplicated in the output: {len(dup)} {dup[:10]}")
    print(f"  in the output but not defined by 1.20: {len(undefined)} {undefined[:12]}")
    print(f"original save baronies {len(orig):,}: kept {kept:,}, renamed {len(renamed)}, taken over by a successor "
          f"{len(successor)} {sorted(successor)}, wasteland {len(wasteland)} {sorted(wasteland)}")
    print(f"  unmapped: {unmapped[:70]}")
    print(f"unmapped: {len(unmapped)}")


if __name__ == "__main__":
    main()
