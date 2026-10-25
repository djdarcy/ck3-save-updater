"""Unit 1 proof: R13 over the whole 1.20 reference against the migrated save.

Per space: mode, base, joins, and the checks the design asks for, computed on the actual translated ids (not
assumed from the construction):
  injective  -- distinct reference ids translate to distinct ids;
  collisions -- translated (non-joined) slot indices that are also save slot indices; must be 0;
  top        -- the highest translated id; must be < 2^32 and never 0xFFFFFFFF.
Then every entry of every copyable kind in the reference is rewritten, and the report lists values translated
per space, fields the schema does not know (unlisted), REVIEW fields, unknown typed-reference types, and
references joined to a pruned campaign character. Finally the counters the transplant must raise.

Usage: python -I tests/one-offs/measure_translation.py <migrated save gamestate> <reference gamestate>
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ck3_save_migrator import idschema as S  # noqa: E402
from ck3_save_migrator import translate as T  # noqa: E402

COPYABLE = [k for k in S.FIELDS if k not in ("character",)] + ["coat_of_arms/coat_of_arms_manager_database"]


def main():
    t0 = time.time()
    save = Path(sys.argv[1]).read_bytes()
    ref = Path(sys.argv[2]).read_bytes()
    tr = T.Translator.build(save, ref)
    print(f"translator built in {time.time() - t0:.0f}s")
    print(f"{'space':22} {'mode':16} {'base':>7} {'ref n':>7} {'joined':>7} {'pruned':>6} {'injective':>9} "
          f"{'collide':>7} {'top id':>14} {'top index':>10}")
    bad = 0
    for sp, m in tr.spaces.items():
        if not m.ref_n:
            continue
        r_ids = T.space_ids(ref, sp)
        s_idx = {i & T.LOW for i in T.space_ids(save, sp)}
        out = {i: m.translate(i) for i in r_ids}
        inj = len(set(out.values())) == len(out)
        offset_idx = {v & T.LOW for i, v in out.items() if i not in m.join and v != i}
        coll = len(offset_idx & s_idx)
        top = max(out.values())
        ok = inj and coll == 0 and top < 2 ** 32 and T.NONE not in out.values()
        bad += not ok
        mode = "identity" if m.identity else ("offset" if m.base else "absent->ident")
        print(f"{sp:22} {mode:16} {m.base:>7,} {m.ref_n:>7,} {len(m.join):>7,} {len(m.join_pruned):>6,} "
              f"{str(inj):>9} {coll:>7} {top:>14,} {max(v & T.LOW for v in out.values()):>10,}"
              f"{'' if ok else '  <-- FAIL'}")
    print(f"spaces failing a check: {bad}")
    print(f"traits: reference {len(tr.trait_map)} positions; {len(tr.new_traits)} names to append to the save's "
          f"traits_lookup, e.g. {tr.new_traits[:5]}")

    t1 = time.time()
    rep = T.RewriteReport()
    n_entries = 0
    nbytes = 0
    for kind in COPYABLE:
        for _, e in T.entries(ref, kind):
            nbytes += len(T.rewrite_entry(ref, e, kind, tr, rep))
            n_entries += 1
    print(f"\nrewrote {n_entries:,} reference entries ({nbytes / 1e6:.0f} MB) in {time.time() - t1:.0f}s")
    print("values translated per space:", dict(rep.translated.most_common()))
    print("id values left unchanged (identity):", dict(rep.unchanged_ids.most_common()))
    print("references joined to a pruned campaign object:", dict(rep.to_pruned))
    print(f"unlisted fields: {sum(rep.unlisted.values())} values in {len(rep.unlisted)} paths")
    for (k, p), n in rep.unlisted.most_common(30):
        print(f"   {k} | {p} | {n}")
    print("REVIEW fields:", dict(rep.review))
    print("unknown typed-reference types:", dict(rep.unknown_types))
    coa = tr.spaces["coat_of_arms"]
    print(f"\ncounters: coat_of_arms/next_id {tr.save_coa_next_id} -> {tr.coa_next_id([coa.translate(i) for i in T.space_ids(ref, 'coat_of_arms')])} "
          f"if every reference coat were added; landed_titles/index {tr.save_title_index}")
    print(f"total {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
