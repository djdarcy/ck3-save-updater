"""Census step 5: where are domiciles referenced from (yurts, camps not carried), what does owner_title name, and
sanity checks on the regiment and county-culture findings of census_followup.py.

Usage: python -I tests/one-offs/census_followup2.py <ref> <ours> <resaved>
"""
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from census_coverage import Save, depth0, holder_of, ents, offset_mode, TITLES, LOW, GEN  # noqa: E402
from census_survey import load  # noqa: E402
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator import translate as T  # noqa: E402


def main():
    R, O, S = (Save(n, load(p)) for n, p in zip(("ref", "ours", "res"), sys.argv[1:4]))
    common = [k for k in R.tid if k in O.tid]
    tbase, _ = offset_mode([(R.tid[k], O.tid[k]) for k in common])
    tr_keys = {k for k in common if (O.tid[k] & GEN) == (R.tid[k] & GEN) and (O.tid[k] & LOW) - (R.tid[k] & LOW) == tbase}
    rt, ot = ents(R.g, TITLES), ents(O.g, TITLES)
    pairs = [(holder_of(R.g, rt[R.tid[k]]), holder_of(O.g, ot[O.tid[k]])) for k in tr_keys]
    cbase, _ = offset_mode([(r, o) for r, o in pairs if r is not None and o is not None])
    c_ref = {r for r in R.chars if ((r & GEN) | ((r & LOW) + cbase)) in O.chars}
    c_ours = {(r & GEN) | ((r & LOW) + cbase) for r in c_ref}

    # domiciles
    dom = dict(T.entries(R.g, "domiciles/database"))
    dtype = {i: depth0(R.g, e, "domicile_type") for i, e in dom.items()}
    ot_vals = Counter()
    for i, e in dom.items():
        v = depth0(R.g, e, "owner_title")
        ot_vals[(dtype[i], "title id" if v and int(v) in R.tkey else "not a title id")] += 1
    print("domicile owner_title:", dict(ot_vals))
    ex = [e for i, e in dom.items() if dtype[i] == "yurt"][0]
    print("yurt example:", R.g[ex.start:ex.start + 500].decode("utf-8", "replace"))
    # who references a yurt / camp id: scan characters and titles for the id after any key
    want = {i for i, t in dtype.items() if t in ("yurt", "camp", "estate")}
    sites = Counter()
    owner_tr = Counter()
    for path in ("living", TITLES, "dynasties/dynasty_house"):
        for i, e in T.entries(R.g, path):
            body = R.g[e.open:e.close]
            for m in re.finditer(rb"\n\t+(\w+)=(\d+)", body):
                v = int(m.group(2))
                if v in want and m.group(1) in (b"domicile", b"owned_domicile", b"home_domicile"):
                    sites[(path, m.group(1).decode(), dtype[v])] += 1
                    if path == "living":
                        owner_tr[(dtype[v], i in c_ref)] += 1
    print("references to yurt/camp/estate ids:", dict(sites))
    print("  (type, referencing character transplanted):", dict(owner_tr))
    # owner_title of yurts: is it a house id?
    houses = {i for i, _ in T.entries(R.g, "dynasties/dynasty_house")}
    for t in ("yurt", "camp", "estate"):
        vals = [int(v) for i, e in dom.items() if dtype[i] == t and (v := depth0(R.g, e, "owner_title"))]
        print(f"  {t}: owner_title values {len(vals)}; in title ids {sum(v in R.tkey for v in vals)}; "
              f"of which transplanted titles {sum(R.tkey.get(v) in tr_keys for v in vals)}; x_ titles "
              f"{sum((R.tkey.get(v) or '').startswith('x_') for v in vals)}")

    # regiments: owners in ours
    regs = list(T.entries(O.g, "armies/regiments"))
    own = [int(v) for _, e in regs if (v := depth0(O.g, e, "owner"))]
    print(f"\nours regiments with owner=: {len(own)}; owner is a character: {sum(o in O.chars for o in own)}; "
          f"owner transplanted: {sum(o in c_ours for o in own)}")
    rregs = list(T.entries(S.g, "armies/regiments"))
    rown = [int(v) for _, e in rregs if (v := depth0(S.g, e, "owner"))]
    print(f"res regiments with owner=: {len(rown)}; owner transplanted: {sum(o in c_ours for o in rown)}")
    # how many transplanted rulers own MAA in ref
    rown_ref = Counter(int(v) for _, e in T.entries(R.g, "armies/regiments") if (v := depth0(R.g, e, "owner")))
    print(f"ref: transplanted characters owning MAA regiments: {sum(1 for c in rown_ref if c in c_ref)}")

    # county culture in res for a missing county
    sr = {e.key.decode(): e for e in gs.iter_entries(S.g, *gs.locate(S.g, "county_manager/counties").body)}
    for k in ("c_BAL_anbyeon", "c_BAL_changchun"):
        e = sr[k]
        print(f"\nres {k}:", S.g[e.start:e.end].decode("utf-8", "replace"))


if __name__ == "__main__":
    main()
