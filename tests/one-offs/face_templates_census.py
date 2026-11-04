"""face_templates_census: where R19's "lost template -> index 0" fallback lands, gene by gene (#40 S4).

For the founding save's layout (1.8.2 vanilla + CFP 3.1.11 + EPE 1.6.0, play7's source) and the target (1.20.1.2 +
the Workshop CFP, EPE and CFP+EPE patch): for every gene R19 carries, the source templates whose names the target
lacks, how many faces use each (dominant or recessive byte), and the name of the target's template 0, which is where
those faces land today. A gene whose template 0 is a `no_*` template is where a face can lose its eyes or teeth.

With an output save as the second argument, also counts that save's faces sitting on a `no_*` template 0 per gene.

Usage: python -I tests/one-offs/face_templates_census.py [<founding save>] [<an R19 output save>]
"""
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
from ck3_save_migrator import dna as D  # noqa: E402
from ck3_save_migrator import savefile as sf  # noqa: E402

P = HERE.parents[1] / "private" / "data"
M23 = P / "originals" / "mods-2023"
SAVE = P / "originals" / "save games" / "Arch-Abbot_Beidh_of_Omni_Church_Council_987_10_27_husband_died.ck3"
WS = Path(r"E:\SteamLibrary\steamapps\workshop\content\1158310")
SOURCE = [("vanilla", P / "versions" / "1.8.2" / "game"), ("cfp", M23 / "cfp_3.1.11"), ("epe", M23 / "epe_1.6.0")]
TARGET = [("vanilla", Path(r"E:\SteamLibrary\steamapps\common\Crusader Kings III\game")),
          ("cfp", WS / "2220098919"), ("epe", WS / "2507209632"), ("patch", WS / "2996881191")]


def faces(path) -> list[bytes]:
    g = sf.read_save(path).gamestate
    return [D.b64d(m.group(1)) for m in re.finditer(rb'\bdna="([^"]*)"', g)]


def main(argv):
    vanilla = "--vanilla-target" in argv          # 1.20.1.2 with no portrait mods (a player without CFP/EPE)
    argv = [a for a in argv if a != "--vanilla-target"]
    src = D.build_layout("source", SOURCE)
    dst = D.build_layout("target", TARGET[:1] if vanilla else TARGET)
    print("target:", "vanilla 1.20.1.2" if vanilla else "1.20.1.2 + Workshop CFP, EPE, patch")
    plan = D.build_plan(src, dst)
    dnas = faces(argv[0] if argv else SAVE)
    print(f"faces {len(dnas)}; plan: kept {plan.kept}, remapped {plan.remapped}, templates_lost {plan.templates_lost}")
    total = 0
    rows = []
    for p, sp, tmap in plan.moves:
        if sp is None or tmap is None:
            continue
        sg, tg = src.genes[sp], dst.genes[p]
        lost = {i: n for n, i in sg["tidx_by_name"].items() if n not in tg["tidx_by_name"]}
        if not lost:
            continue
        use = Counter()
        for d in dnas:
            if len(d) >= sp * 4 + 4:
                for b in (d[sp * 4], d[sp * 4 + 2]):
                    if b in lost:
                        use[b] += 1
        t0 = next((n for n, i in tg["tidx_by_name"].items() if i == 0), "?")
        n = sum(use.values())
        total += n
        rows.append((n, tg["name"], t0, {lost[i]: c for i, c in use.items()}, sorted(lost.values())))
    print(f"template bytes that fall to index 0: {total}\n")
    for n, name, t0, used, lost in sorted(rows, reverse=True):
        flag = "  <-- template 0 is a no_ template" if t0.startswith("no_") else ""
        print(f"{n:7}  {name:34} target template 0 = {t0}{flag}")
        print(f"         lost: {lost}; used: {used}")
    if len(argv) > 1:
        out = faces(argv[1])
        nos = [(p, g["name"], next((nn for nn, i in g["tidx_by_name"].items() if i == 0), ""))
               for p, g in enumerate(dst.genes) if g.get("tidx_by_name")]
        nos = [(p, n, t0) for p, n, t0 in nos if t0.startswith("no_")]
        print(f"\nin {Path(argv[1]).name} ({len(out)} faces): faces with a dominant byte on a no_ template 0")
        for p, n, t0 in nos:
            c = sum(1 for d in out if len(d) >= p * 4 + 4 and d[p * 4] == 0)
            print(f"  {n:34} {t0:24} {c}")


if __name__ == "__main__":
    main(sys.argv[1:])
