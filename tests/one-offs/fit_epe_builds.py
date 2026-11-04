"""fit_epe_builds: which EPE build were the founding 1.8.1 save's faces written with? (issue #40, hypothesis 2)

Every dna= string in the save (712 characters = 133 places) is fitted against candidate source layouts with
dna_layout.fit: a template byte higher than its gene's highest template index is impossible. A layout that explains
the faces has 0 impossible places over the places it covers; the question is which layout covers all 133.

Known answers (2026-10-25 decode note): 1.8.2 + CFP 3.1.11 + EPE 1.6.0, file order: 0 impossible over places 0-129;
the same genes in category-grouped order: 7 impossible (the control arm: it must show impossible places).

Usage: python -I tests/one-offs/fit_epe_builds.py
"""
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1]))
import dna_layout as D  # noqa: E402
import dna_whole_save as W  # noqa: E402
from ck3_save_migrator import savefile as sf  # noqa: E402

P = HERE.parents[1] / "private" / "data"
SAVE = P / "originals" / "save games" / "Arch-Abbot_Beidh_of_Omni_Church_Council_987_10_27_husband_died.ck3"
V182 = ("vanilla", P / "versions" / "1.8.2" / "game")
M23 = P / "originals" / "mods-2023"
CFP, E160, E181 = ("cfp", M23 / "cfp_3.1.11"), ("epe", M23 / "epe_1.6.0"), ("epe", M23 / "epe_1.8.1")


def faces() -> list[bytes]:
    g = sf.read_save(SAVE).gamestate
    return [W.b64d(m.group(1)) for m in re.finditer(rb'\bdna="([^"]*)"', g)]


def report(name, order, dnas):
    places = min(d.__len__() for d in dnas) // 4
    bad, lines = D.fit(order, dnas)
    bad_places = [ln.split()[0] for ln in lines if "IMPOSSIBLE" in ln]
    print(f"{name:52} genes {len(order):3}  places fitted {min(len(order), places):3}  impossible {bad:2}  "
          f"first impossible places {bad_places[:6]}")
    return order


def main():
    dnas = faces()
    lens = {len(d) for d in dnas}
    print(f"faces: {len(dnas)}; decoded byte lengths {sorted(lens)} (places {sorted(n // 4 for n in lens)})")
    a = D.dna_order(D.load_layout([V182, CFP, E160]))
    b = D.dna_order(D.load_layout([V182, CFP, E181]))
    report("(a) 1.8.2 + CFP 3.1.11 + EPE 1.6.0, file order", a, dnas)
    report("control: (a) in category-grouped order", D.dna_order(D.load_layout([V182, CFP, E160]), "grouped"), dnas)
    report("(b) 1.8.2 + CFP 3.1.11 + EPE 1.8.1, file order", b, dnas)
    report("(b') 1.8.2 + EPE 1.8.1 (no CFP)", D.dna_order(D.load_layout([V182, E181])), dnas)
    names_a = [g["name"] for g in a]
    extra = [g for g in b if g["name"] not in set(names_a)]
    hybrid = a + extra
    report("(c) hybrid: (a), then EPE 1.8.1's extra genes", hybrid, dnas)
    print("\ngenes at places 126-134:")
    for p in range(126, 135):
        ga = a[p]["name"] if p < len(a) else "-"
        gb = b[p]["name"] if p < len(b) else "-"
        gc = hybrid[p]["name"] if p < len(hybrid) else "-"
        print(f"  {p:3}  (a) {ga:34} (b) {gb:34} (c) {gc}")
    print(f"\nEPE 1.8.1 genes not in (a): {[g['name'] for g in extra]}")
    print(f"(a) genes not in EPE 1.8.1 layout (b): {[n for n in names_a if n not in {g['name'] for g in b}]}")


def subsets():
    """Every ordered choice of 3 of EPE 1.8.1's 5 extra genes appended after (a): which fit places 130-132?
    Colour genes have no template check in dna_layout.fit, so a colour gene always 'fits'; the report says which."""
    from itertools import permutations
    dnas = faces()
    a = D.dna_order(D.load_layout([V182, CFP, E160]))
    b = D.dna_order(D.load_layout([V182, CFP, E181]))
    extra = [g for g in b if g["name"] not in {x["name"] for x in a}]
    print("extra genes:", [(g["name"], g["cat"], g["tmax"]) for g in extra])
    fits = []
    for trio in permutations(extra, 3):
        bad, _ = D.fit(a + list(trio), dnas)
        if bad == 0:
            fits.append([g["name"] for g in trio])
    print(f"ordered triples tried: {len(list(permutations(extra, 3)))}; with 0 impossible places: {len(fits)}")
    for f in fits:
        print("  ", f)
    for p in (130, 131, 132):
        print(f"place {p}: max template byte seen {max(max(d[p * 4], d[p * 4 + 2]) for d in dnas)}")


def addons():
    """(a) plus each other gene-shipping mod copy we hold, in the order the launcher would load it after EPE."""
    dnas = faces()
    o = P / "originals"
    cands = {
        "+ ugc_2507220129 (2022.06.21)": [("u", o / "mods-2022.06.21" / "2507220129")],
        "+ ugc_2507220129 (2022.03.30)": [("u", o / "mods-2022.03.30" / "2507220129")],
        "+ CFP_EPE_CBO_compatibility": [("x", M23 / "CFP_EPE_CBO_compatibility")],
        "+ char_body_overhaul": [("x", M23 / "char_body_overhaul")],
        "+ char_body_overhaul + cbo_cfp_compatibility": [("x", M23 / "char_body_overhaul"),
                                                         ("y", M23 / "cbo_cfp_compatibility")],
    }
    for name, extra in cands.items():
        report(f"(a) {name}", D.dna_order(D.load_layout([V182, CFP, E160] + extra)), dnas)


def candidates(paths: list[str]):
    """1.8.2 vanilla + CFP 3.1.11 + each given EPE folder (read only, wherever it is), file order."""
    dnas = faces()
    for p in paths:
        report(f"EPE {Path(p).parent.name}/{Path(p).name}"[:52], D.dna_order(D.load_layout([V182, CFP, ("epe", Path(p))])),
               dnas)


def vanilla():
    """Does a mod file in (a) hide vanilla genes? The 10-25 decode: 1.7.2 -> 1.8.1 appended two genes with no mod
    change, so they are vanilla 1.8 genes. List vanilla 1.8.2's DNA genes missing from (a), the file that defines
    each and which layer's copy of that file (a) loads, then fit (a) with the hidden genes appended."""
    from itertools import permutations
    dnas = faces()
    van = D.dna_order(D.load_layout([V182]))
    a_genes = D.load_layout([V182, CFP, E160])
    a = D.dna_order(a_genes)
    names_a = {g["name"] for g in a}
    files_a = {g["file"]: g["src"] for g in a_genes.values()}
    hidden = [g for g in van if g["name"] not in names_a]
    print(f"vanilla 1.8.2 DNA genes {len(van)}; (a) DNA genes {len(a)}; vanilla genes missing from (a): {len(hidden)}")
    for g in hidden:
        print(f"  {g['name']:40} {g['cat']:16} tmax {g['tmax']}  file {g['file']}  (a) loads that file from: "
              f"{files_a.get(g['file'], '-')}")
    report("(a) as is", a, dnas)
    report("(a) + hidden vanilla genes, vanilla file order", a + hidden, dnas)
    if 0 < len(hidden) <= 6:
        fits = [[g["name"] for g in p] for p in permutations(hidden, min(3, len(hidden)))
                if D.fit(a + list(p), dnas)[0] == 0]
        print(f"ordered choices of {min(3, len(hidden))} hidden genes after (a) with 0 impossible: {len(fits)}")
        for f in fits[:20]:
            print("  ", f)
    for p in (130, 131, 132):
        print(f"place {p}: max template byte seen {max(max(d[p * 4], d[p * 4 + 2]) for d in dnas)}")


def v172():
    """Vanilla 1.7.2 (branch fetch, 2026-11-03) against 1.8.2: same DNA genes in the same order? Then fit the 1.7.2
    save's faces (987_07_01_sleep, 131 places) with 1.7.2 + CFP 3.1.11 + EPE 1.6.0."""
    v172 = ("vanilla", P / "versions" / "1.7.2" / "game")
    o172 = [g["name"] for g in D.dna_order(D.load_layout([v172]))]
    o182 = [g["name"] for g in D.dna_order(D.load_layout([V182]))]
    print(f"vanilla DNA genes: 1.7.2 {len(o172)}, 1.8.2 {len(o182)}; same names in same order: {o172 == o182}")
    print(f"  only in 1.7.2: {[n for n in o172 if n not in o182]}; only in 1.8.2: {[n for n in o182 if n not in o172]}")
    save = P / "originals" / "save games" / "Arch-Abbot_Beidh_of_Omni_Church_Council_987_07_01_sleep.ck3"
    g = sf.read_save(save).gamestate
    dnas = [W.b64d(m.group(1)) for m in re.finditer(rb'\bdna="([^"]*)"', g)]
    print(f"1.7.2 save faces: {len(dnas)}; places {sorted({len(d) // 4 for d in dnas})}")
    report("1.7.2 + CFP 3.1.11 + EPE 1.6.0 on the 1.7.2 save", D.dna_order(D.load_layout([v172, CFP, E160])), dnas)
    report("control: grouped order on the 1.7.2 save",
           D.dna_order(D.load_layout([v172, CFP, E160]), "grouped"), dnas)
    for p in (129, 130):
        print(f"1.7.2 save place {p}: max template byte seen {max(max(d[p * 4], d[p * 4 + 2]) for d in dnas)}")


GMODS = Path("G:/F/Dustins Stuff/Applications & Software data/Games/Crusader Kings 3/Mods")


def cfp315():
    """The save's own CFP (local 3.1.5; copy found 2026-11-03 at G: Mods/2023.09.01/mod/__old/cfp_3.1.5, read only)
    with each EPE copy we hold, fitted on the 1.7.2 save (131 places) and the 1.8.1 save (133). Vanilla 1.8.2's
    face genes equal 1.7.2's (--v172), so 1.8.2 stands in for both. CFP 3.1.11 rows are the known baseline."""
    saves = {
        "1.7.2": P / "originals" / "save games" / "Arch-Abbot_Beidh_of_Omni_Church_Council_987_07_01_sleep.ck3",
        "1.8.1": SAVE,
    }
    faces_by = {}
    for k, s in saves.items():
        g = sf.read_save(s).gamestate
        faces_by[k] = [W.b64d(m.group(1)) for m in re.finditer(rb'\bdna="([^"]*)"', g)]
    cfps = {"cfp 3.1.5": ("cfp", GMODS / "2023.09.01" / "mod" / "__old" / "cfp_3.1.5"), "cfp 3.1.11": CFP}
    w = "steam workshop content 1158310"
    epes = {
        "epe_1.6.0": E160[1], "epe_1.8.1": E181[1],
        "G 2022.02.25": GMODS / "2022.02.25" / "mod_normal_backup" / "2507209632",
        "G 2022.03.10 Copy": GMODS / "2022.03.10" / "2507209632 - Copy",
        "G 2022.03.11": GMODS / "2022.03.11" / "2507209632",
        "G 2022.03.30": GMODS / "2022.03.30" / "mod_normal_backup" / "2507209632",
        "G 2022.06.05 _test": GMODS / "2022.06.05" / "mod_normal_backup" / "2507209632_test",
        "G 2022.06.10": GMODS / "2022.06.10" / "mod_normal" / w / "2507209632",
        "G 2022.06.10 _test": GMODS / "2022.06.10" / "mod_normal" / w / "2507209632_test",
        "G 2022.06.21": GMODS / "2022.06.21" / "mod_normal" / "2507209632",
    }
    patch = ("patch", GMODS / "2022.06.21" / "mod_normal" / "2507220129")
    for cname, c in cfps.items():
        for ename, e in epes.items():
            for with_patch in (False, True):
                layers = [V182, c, ("epe", e)] + ([patch] if with_patch else [])
                order = D.dna_order(D.load_layout(layers))
                for k, dnas in faces_by.items():
                    report(f"{k} | {cname} + {ename}{' + patch' if with_patch else ''}"[:52], order, dnas)


def changelog_trio():
    """The EPE Workshop changelog (2507209632, read 2026-11-03): Sep 2022 (1.7) Salt and Pepper re-enabled, Dec 2
    2022 'Lower Eyelid Size gene added', Dec 8 2022 'New Eye Shape gene'. Hypothesis: places 130-132 are hair_aging,
    gene_bs_eye_lower_lid_size, gene_bs_eye_shape, appended in that order. Fit (a) + the trio on both saves, and
    count the template bytes seen per tail place (a gene's template count is its tmax + 1)."""
    from collections import Counter
    b = {g["name"]: g for g in D.dna_order(D.load_layout([V182, CFP, E181]))}
    a = D.dna_order(D.load_layout([V182, CFP, E160]))
    trio = [b["hair_aging"], b["gene_bs_eye_lower_lid_size"], b["gene_bs_eye_shape"]]
    print("trio as EPE 1.8.1 defines them:", [(g["name"], g["templates"], g["tmax"]) for g in trio])
    saves = {"1.7.2": P / "originals" / "save games" / "Arch-Abbot_Beidh_of_Omni_Church_Council_987_07_01_sleep.ck3",
             "1.8.1 (987_07_01_1.8.1_update)": P / "originals" / "save games" /
             "Arch-Abbot_Beidh_of_Omni_Church_Council_987_07_01_1.8.1_update.ck3",
             "1.8.1 (987_10_27)": SAVE}
    for k, s in saves.items():
        g = sf.read_save(s).gamestate
        dnas = [W.b64d(m.group(1)) for m in re.finditer(rb'\bdna="([^"]*)"', g)]
        n = min(len(d) for d in dnas) // 4
        report(f"{k} | (a) + trio"[:52], a + trio, dnas)
        for p in range(130, n):
            c = Counter((d[p * 4], d[p * 4 + 2]) for d in dnas)
            print(f"   place {p}: (template byte, recessive template byte) counts {sorted(c.items())[:8]}")


def layer(folder: str):
    """S2 unit 4's proof: vanilla 1.8.2 + CFP 3.1.5 (the save's) + EPE 1.6.0 + the tail layer folder; expected 0
    impossible on the 1.7.2 save (131 places) and 1 (place 132, the 14 faces with eye-shape template 2) on 987_10_27."""
    c315 = ("cfp", P / "mods-archive" / "cfp_3.1.5")
    order = D.dna_order(D.load_layout([V182, c315, E160, ("tail", Path(folder))]))
    print("last genes:", [g["name"] for g in order[-4:]], f"({len(order)} genes)")
    for k, s in {"1.7.2": P / "originals" / "save games" / "Arch-Abbot_Beidh_of_Omni_Church_Council_987_07_01_sleep.ck3",
                 "987_10_27": SAVE}.items():
        g = sf.read_save(s).gamestate
        report(f"{k} | 1.8.2 + CFP 3.1.5 + EPE 1.6.0 + layer", order,
               [W.b64d(m.group(1)) for m in re.finditer(rb'\bdna="([^"]*)"', g)])


if __name__ == "__main__":
    if "--layer" in sys.argv:
        layer(sys.argv[sys.argv.index("--layer") + 1])
    elif "--trio" in sys.argv:
        changelog_trio()
    elif "--cfp315" in sys.argv:
        cfp315()
    elif "--v172" in sys.argv:
        v172()
    elif "--vanilla" in sys.argv:
        vanilla()
    elif "--candidates" in sys.argv:
        candidates(sys.argv[sys.argv.index("--candidates") + 1:])
    else:
        subsets() if "--subsets" in sys.argv else addons() if "--addons" in sys.argv else main()
