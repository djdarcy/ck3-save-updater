"""Census step 4: settle the anomalies of census_coverage.py.

  1. county records the engine wrote on load (RES) for the transplanted counties ours lacks, versus the
     reference's: culture compared by culture TEMPLATE (culture ids differ between saves), rite (identity space),
     development; and the transplanted counties the reference itself has no record for;
  2. regiments the reference's transplanted people own (owner=): carried with the owner dropped, or not carried?
  3. mercenary companies attributed by county= and culture=;
  4. domiciles: which field names their owner, and how many the transplant left out.

Usage: python -I tests/one-offs/census_followup.py <ref> <ours> <resaved>
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

    # 1. county records
    tmpl = {s.name: {i: depth0(s.g, e, "culture_template") for i, e in T.entries(s.g, "culture_manager/cultures")}
            for s in (R, O, S)}

    def recs(s):
        return {e.key.decode(): e for e in gs.iter_entries(s.g, *gs.locate(s.g, "county_manager/counties").body)}
    rr, orr, sr = recs(R), recs(O), recs(S)
    miss = sorted(k for k in rr if k in tr_keys and k not in orr)
    cmp = Counter()
    examples = []
    for k in miss:
        r, s = rr[k], sr.get(k)
        if s is None:
            cmp["absent in res"] += 1
            continue
        rc = tmpl["ref"].get(int(depth0(R.g, r, "culture") or -1))
        sc = tmpl["res"].get(int(depth0(S.g, s, "culture") or -1))
        cmp[("culture", rc == sc)] += 1
        cmp[("rite", depth0(R.g, r, "rite") == depth0(S.g, s, "rite"))] += 1
        rd, sd = float(depth0(R.g, r, "development") or 0), float(depth0(S.g, s, "development") or 0)
        cmp[("development", "same" if rd == sd else "lower" if sd < rd else "higher")] += 1
        if rc != sc and len(examples) < 12:
            examples.append((k, rc, sc, depth0(R.g, r, "rite"), depth0(S.g, s, "rite"), rd, sd))
    print(f"1. transplanted counties with a ref record that ours lacks: {len(miss)}")
    print("   engine-written (res) vs reference:", dict(cmp))
    for x in examples:
        print("     ", x)
    tr_c = {k for k in tr_keys if k.startswith("c_")}
    norec = sorted(tr_c - rr.keys())
    print(f"   transplanted c_ titles with no ref county record: {len(norec)} e.g. {norec[:8]}")
    # are those real counties? their de_jure_vassals (baronies) in the ref
    with_b = sum(1 for k in norec if re.search(rb"\n\tde_jure_vassals=", R.g[rt[R.tid[k]].open:rt[R.tid[k]].close]))
    held = sum(1 for k in norec if holder_of(R.g, rt[R.tid[k]]) is not None)
    print(f"   of those: with de jure vassals {with_b}, held {held}")
    extra = sorted(k for k in orr if k not in rr)
    print(f"   ours records the ref lacks: {len(extra)} {extra[:8]}")

    # 2. regiments
    owned = {i: e for i, e in T.entries(R.g, "armies/regiments") if (v := depth0(R.g, e, "owner")) and int(v) in c_ref}
    print(f"\n2. ref regiments owned by transplanted people: {len(owned)}")
    # who references them in the ref (titles owned_maa / controlled_maa, characters, provinces)?
    ids = set(owned)
    refby = Counter()
    for path in (TITLES, "provinces", "living"):
        for i, e in T.entries(R.g, path):
            body = R.g[e.open:e.close]
            for m in re.finditer(rb"\n\t+(owned_maa|controlled_maa|garrison|levy|regiments)=\{?([^}\n]*)", body):
                for x in m.group(2).split():
                    if x.isdigit() and int(x) in ids:
                        refby[(path, m.group(1).decode())] += 1
    print("   referenced from:", dict(refby))
    ex = next(iter(owned.values()))
    print("   example:", R.g[ex.start:ex.start + 400].decode("utf-8", "replace"))
    # ours: regiments above the save's regiment high-water whose owner field is missing / present
    regs = ents(O.g, "armies/regiments")
    rbase, _ = offset_mode([])
    hi = sorted(regs)[-3002:]
    own = Counter("owner" if depth0(O.g, regs[i], "owner") else "no owner" for i in hi)
    print("   ours, the 3,002 highest regiment ids (the carried ones):", dict(own))
    ref_own = Counter("owner" if depth0(R.g, e, "owner") else "no owner" for _, e in T.entries(R.g, "armies/regiments"))
    print("   ref, all regiments:", dict(ref_own))

    # 3. mercenaries
    print("\n3. mercenary companies")
    new_t = set(tmpl["ours"].values()) - set(tmpl["res"].values()) | set()
    for s in (R, O, S):
        es = list(T.entries(s.g, "mercenary_company_manager/mercenary_companies"))
        by_county = sum(1 for _, e in es if (v := depth0(s.g, e, "county")) and s.tkey.get(int(v)) in tr_keys)
        cul = Counter(tmpl[s.name].get(int(v)) if (v := depth0(s.g, e, "culture")) else None for _, e in es)
        print(f"   {s.name}: {len(es)}; county in transplanted titles: {by_county}")
        if s is R:
            ref_cul = cul
        else:
            gap = {k: n - cul.get(k, 0) for k, n in ref_cul.items() if n > cul.get(k, 0)}
            print(f"     cultures with fewer companies than ref: {len(gap)} ({sum(gap.values())} companies) "
                  f"e.g. {sorted(gap.items(), key=lambda x: -x[1])[:10]}")
    ex = next(iter(T.entries(R.g, "mercenary_company_manager/mercenary_companies")))[1]
    print("   example:", R.g[ex.start:ex.start + 300].decode("utf-8", "replace"))

    # 4. domiciles
    print("\n4. domiciles")
    es = list(T.entries(R.g, "domiciles/database"))
    keys = Counter()
    for _, e in es[:50]:
        for c in gs.iter_children(R.g, *e.body):
            keys[c.key.decode() if c.key else None] += 1
    print("   ref domicile fields (first 50):", dict(keys))
    for f in ("owner", "domicile_owner", "house", "dynasty_house"):
        vals = [depth0(R.g, e, f) for _, e in es]
        n = sum(1 for v in vals if v)
        if n:
            print(f"   field {f}: {n} entries; owner transplanted: {sum(1 for v in vals if v and int(v) in c_ref)}")
    types = Counter(depth0(R.g, e, "domicile_type") for _, e in es)
    print("   ref domicile types:", dict(types))
    otypes = Counter(depth0(O.g, e, "domicile_type") for _, e in T.entries(O.g, "domiciles/database"))
    print("   ours domicile types:", dict(otypes))


if __name__ == "__main__":
    main()
