"""Census step 3: for every database of the 1.20 reference, does our output carry the entries that belong to the
things the transplant added (titles, provinces, people)? Four witnesses:

  REF   the vanilla 1.20 reference save (the transplant's source);
  OURS  our migrated output (MIGRATE_TEST__e2e5b_faith == MIGRATE_TEST__dna_poc_control, byte-identical);
  RES   the game's own load-and-save of OURS (MIGRATE_TEST__dna_poc_control__resaved): what the engine fills on load;
  CHAIN the campaign loaded by the engine through 1.18.4 -> 1.19.0 -> 1.20.1.2 (no transplant; the engine added
        titles and county records but no people).

The transplanted sets, measured from the outputs (no pre-transplant gamestate is kept):
  titles     keys in both REF and OURS whose OURS id is REF id + the title offset (R13: index + base, generation
             kept); the base is the mode of the index differences;
  characters REF characters whose offset-translated id is a character in OURS (base: mode over the holders of the
             transplanted titles);
  provinces  REF province ids absent from the original 1.8.1 save.
The engine keeps a live object's id across a save (translate.py), so OURS ids apply to RES.

Usage: python -I tests/one-offs/census_coverage.py <ref> <ours> <resaved> <chain> <orig_1.8.1> <out.json>
"""
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from census_survey import load  # noqa: E402
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator import translate as T  # noqa: E402

TITLES = "landed_titles/landed_titles"
CHARS = ("living", "dead_unprunable", "characters/dead_prunable")
LOW, GEN = T.LOW, T.GEN


def depth0(g, e, field):
    rx = re.compile(rb"\n\t+" + re.escape(field.encode()) + rb"=\"?([^\"\s{}]+)\"?")
    v = T._depth0(g, e, rx, head=1 << 20)
    return v.decode() if v else None


def depth0_all(g, e, field):
    """Every value of ``field`` anywhere in the entry (for nested ``county=`` in title_members)."""
    return [m.decode() for m in re.findall(rb"\n\t+" + re.escape(field.encode()) + rb"=(\d+)", g[e.open:e.close])]


def ents(g, path):
    return dict(T.entries(g, path))


def first_existing(g, *paths):
    for p in paths:
        try:
            return p, gs.locate(g, p)
        except gs.GamestateError:
            continue
    return None, None


def bare_list(g, path):
    try:
        b = gs.locate(g, path)
    except gs.GamestateError:
        return None
    return re.findall(rb"[^\s{}]+", g[b.open + 1:b.close])


def scalar_map(g, path):
    try:
        b = gs.locate(g, path)
    except gs.GamestateError:
        return None
    return {k.decode(): v.decode() for k, v in re.findall(rb"\n\t*([^\s={}]+)=([^\s{}]+)", g[b.open:b.close + 1])}


class Save:
    def __init__(self, name, g):
        self.name, self.g = name, g
        self.tkey = {i: (k.decode() if (k := T._depth0(g, e, T._KEY)) else None) for i, e in T.entries(g, TITLES)}
        self.tid = {k: i for i, k in self.tkey.items() if k}
        self.chars = set()
        for p in CHARS:
            self.chars |= {i for i, _ in T.entries(g, p)}
        self.provinces = {i for i, _ in T.entries(g, "provinces")}


def holder_of(g, e):
    m = re.search(rb"\n\tholder=(\d+)", g[e.open:min(e.close, e.open + 4096)])
    return int(m.group(1)) if m and int(m.group(1)) != T.NONE else None


def offset_mode(pairs):
    c = Counter((o & LOW) - (r & LOW) for r, o in pairs if (o & GEN) == (r & GEN))
    return c.most_common(1)[0] if c else (None, 0)


def main():
    t0 = time.time()
    a = sys.argv[1:]
    R, O, S, C = (Save(n, load(p)) for n, p in zip(("ref", "ours", "res", "chain"), a[:4]))
    orig = load(a[4])
    orig_prov = {i for i, _ in T.entries(orig, "provinces")}
    del orig
    print(f"loaded in {time.time() - t0:.0f}s")

    # --- transplanted titles
    common = [k for k in R.tid if k in O.tid]
    tbase, tn = offset_mode([(R.tid[k], O.tid[k]) for k in common])
    tr_keys = {k for k in common if (O.tid[k] & GEN) == (R.tid[k] & GEN)
               and (O.tid[k] & LOW) - (R.tid[k] & LOW) == tbase}
    print(f"title base {tbase} ({tn} keys); transplanted titles {len(tr_keys)} "
          f"(counties {sum(1 for k in tr_keys if k.startswith('c_'))})")
    # --- transplanted characters
    rt, ot = ents(R.g, TITLES), ents(O.g, TITLES)
    pairs = [(holder_of(R.g, rt[R.tid[k]]), holder_of(O.g, ot[O.tid[k]])) for k in tr_keys]
    pairs = [(r, o) for r, o in pairs if r is not None and o is not None]
    cbase, cn = offset_mode(pairs)

    def ctr(r):
        return (r & GEN) | ((r & LOW) + cbase)
    c_ref = {r for r in R.chars if ctr(r) in O.chars}
    c_ours = {ctr(r) for r in c_ref}
    print(f"character base {cbase} ({cn} holder pairs); transplanted characters {len(c_ref)}; "
          f"in res {len(c_ours & S.chars)}")
    tr_prov = R.provinces - orig_prov
    print(f"transplanted provinces {len(tr_prov)}")

    t_ref = {R.tid[k] for k in tr_keys}
    t_ours = {O.tid[k] for k in tr_keys}
    t_res = {S.tid[k] for k in tr_keys if k in S.tid}
    t_chain = {C.tid[k] for k in tr_keys if k in C.tid}
    TSET = {"ref": t_ref, "ours": t_ours, "res": t_res, "chain": t_chain}
    CSET = {"ref": c_ref, "ours": c_ours, "res": c_ours, "chain": set()}
    saves = {"ref": R, "ours": O, "res": S, "chain": C}
    rows = []

    def row(name, kind, consulted, counts, tr, note=""):
        rows.append({"db": name, "key_kind": kind, "consulted": consulted, "counts": counts, "transplanted": tr,
                     "note": note})
        print(f"{name:52} {kind:24} {json.dumps(counts):60} tr={json.dumps(tr)} {note}")

    # 1. keyed by title key
    for path in ("county_manager/counties",):
        keys = {n: {e.key.decode() for e in gs.iter_entries(s.g, *gs.locate(s.g, path).body)}
                for n, s in saves.items()}
        exp = keys["ref"] & tr_keys
        row(path, "title key", "n", {n: len(v) for n, v in keys.items()},
            {"ref_for_tr": len(exp), "ours": len(exp & keys["ours"]), "res": len(exp & keys["res"]),
             "chain": len(exp & keys["chain"])})
        miss = sorted(exp - keys["ours"])
        print("   missing e.g.", miss[:10])
        # what the engine wrote for the missing ones, versus the reference
        rc = {e.key.decode(): e for e in gs.iter_entries(R.g, *gs.locate(R.g, path).body)}
        sc = {e.key.decode(): e for e in gs.iter_entries(S.g, *gs.locate(S.g, path).body)}
        diff = Counter()
        for k in miss:
            if k in sc:
                for f in ("culture", "faith", "rite", "development", "county_control"):
                    rv, sv = depth0(R.g, rc[k], f), depth0(S.g, sc[k], f)
                    diff[(f, "same" if rv == sv else "differs")] += 1
        print("   engine-filled vs reference, for the missing:", dict(diff))
    for path in ("county_manager/monthly_change", "county_manager/monthly_increase"):
        row(path, "positional (parallel to counties)", "n",
            {n: (len(v) if (v := bare_list(s.g, path)) is not None else None) for n, s in saves.items()}, {})
    # name map: title keys, dynasty/house keys, history ids
    nm = {n: scalar_map(s.g, "coat_of_arms/coat_of_arms_manager_name_map") for n, s in saves.items()}
    exp = {k for k in nm["ref"] if k in tr_keys}
    row("coat_of_arms/coat_of_arms_manager_name_map [title keys]", "title key -> coat id", "n",
        {n: sum(1 for k in v if re.match(r"^[bcdkeh]_", k)) for n, v in nm.items()},
        {"ref_for_tr": len(exp), "ours": len(exp & nm["ours"].keys()), "res": len(exp & nm["res"].keys()),
         "chain": len(exp & nm["chain"].keys())})
    dkeys = {}
    for n, s in saves.items():
        ks = set()
        for p in ("dynasties/dynasties", "dynasties/dynasty_house"):
            for i, e in T.entries(s.g, p):
                if (k := depth0(s.g, e, "key")):
                    ks.add(k)
        dkeys[n] = ks
    new_dkeys = dkeys["ours"] - dkeys["chain"]
    exp = {k for k in nm["ref"] if k in new_dkeys}
    row("coat_of_arms/coat_of_arms_manager_name_map [dynasty/house keys]", "dynasty/house key -> coat id", "n",
        {n: sum(1 for k in v if not re.match(r"^[bcdkeh]_", k)) for n, v in nm.items()},
        {"carried_dyn_house_keys": len(new_dkeys), "ref_for_tr": len(exp), "ours": len(exp & nm["ours"].keys()),
         "res": len(exp & nm["res"].keys()), "chain": len(exp & nm["chain"].keys())})

    # 2. positional id lists
    def dyn_by_key(s, p):
        return {i: depth0(s.g, e, "key") for i, e in T.entries(s.g, p)}
    for path, src in (("dynasties/static_dynasties", "dynasties/dynasties"),
                      ("dynasties/static_dynasty_houses", "dynasties/dynasty_house")):
        out, tr = {}, {}
        for n, s in saves.items():
            lst = bare_list(s.g, path) or []
            out[n] = len(lst)
            km = dyn_by_key(s, src)
            tr[n] = sum(1 for x in lst if x.isdigit() and km.get(int(x)) in new_dkeys)
        row(path, "positional list of dynasty/house ids", "n", out,
            {"ref_for_tr": tr["ref"], "ours": tr["ours"], "res": tr["res"], "chain": tr["chain"]})
    tmpl = {n: {i: depth0(s.g, e, "culture_template") for i, e in T.entries(s.g, "culture_manager/cultures")}
            for n, s in saves.items()}
    new_t = set(tmpl["ours"].values()) - set(tmpl["chain"].values())
    out, tr = {}, {}
    for n, s in saves.items():
        lst = bare_list(s.g, "culture_manager/template_cultures") or []
        out[n] = len(lst)
        tr[n] = sum(1 for x in lst if x.isdigit() and tmpl[n].get(int(x)) in new_t)
    row("culture_manager/template_cultures", "positional list of culture ids", "n", out,
        {"new_templates": len(new_t), "ref_for_tr": tr["ref"], "ours": tr["ours"], "res": tr["res"],
         "chain": tr["chain"]})
    # positional check: is template_cultures[i] == culture id i in the reference?
    lst = bare_list(R.g, "culture_manager/template_cultures")
    print("   ref template_cultures is 0..n-1:", [int(x) for x in lst] == list(range(len(lst))))

    # 3. keyed by character id
    for path in ("ai/ai_strategies", "living", "dead_unprunable"):
        keys = {n: {i for i, _ in T.entries(s.g, path)} for n, s in saves.items()}
        exp = keys["ref"] & c_ref
        row(path, "character id", "y", {n: len(v) for n, v in keys.items()},
            {"ref_for_tr": len(exp), "ours": len(keys["ours"] & c_ours), "res": len(keys["res"] & c_ours)})
    cl = {n: T.character_lookup(s.g) for n, s in saves.items()}
    row("character_lookup", "history id -> character id", "y", {n: len(v) for n, v in cl.items()},
        {"ref_for_tr": sum(1 for v in cl["ref"].values() if v in c_ref),
         "ours": sum(1 for v in cl["ours"].values() if v in c_ours),
         "res": sum(1 for v in cl["res"].values() if v in c_ours)})
    ql = {n: bare_list(s.g, "council_task_manager/queue") for n, s in saves.items()}
    row("council_task_manager/queue", "list of character ids", "n",
        {n: (len(v) if v is not None else None) for n, v in ql.items()},
        {"ref_for_tr": sum(1 for x in ql["ref"] or [] if int(x) in c_ref),
         "res": sum(1 for x in ql["res"] or [] if int(x) in c_ours)})

    # 4. own-id databases, attributed through a field
    owned = [
        ("council_task_manager/active", ("council_task_manager/active",), "court_owner", "char", "y"),
        ("court_positions/database", ("court_positions/database",), "employer", "char", "y"),
        ("important_action_manager/active", ("important_action_manager/active",), "character", "char", "n"),
        ("stories/active", ("stories/active",), "owner", "char", "n"),
        ("faction_manager/factions [target]", ("faction_manager/factions",), "target", "char", "n"),
        ("artifacts/artifacts", ("artifacts/artifacts",), "owner", "char", "y"),
        ("armies/regiments", ("armies/regiments",), "owner", "char", "y"),
        ("vassal_contracts", ("vassal_contracts/database", "vassal_contracts/active"), "vassal", "char", "y"),
        ("tax_slot_manager/database", ("tax_slot_manager/database",), "liege", "char", "y"),
        ("diarchies/database", ("diarchies/database",), "liege", "char", "y"),
        ("dynasties/dynasty_house", ("dynasties/dynasty_house",), "head_of_house", "char", "y"),
        ("dynasties/dynasties", ("dynasties/dynasties",), "dynasty_head", "char", "y"),
        ("culture_manager/cultures", ("culture_manager/cultures",), "head", "char", "y"),
        ("domiciles/database", ("domiciles/database",), "owner_title", "title", "y"),
        ("clerical_region_manager/database", ("clerical_region_manager/database",), "title", "title", "y"),
        ("holy_orders/holy_orders", ("holy_orders/holy_orders",), "title", "title", "y"),
        ("mercenary_company_manager/mercenary_companies", ("mercenary_company_manager/mercenary_companies",),
         "title", "title", "n"),
        ("struggle_manager/database", ("struggle_manager/database",), "struggle_type", "none", "n"),
        ("situation_manager/database", ("situation_manager/database",), "situation_type", "none", "y"),
    ]
    for name, paths, field, sp, cons in owned:
        counts, tr = {}, {}
        for n, s in saves.items():
            p, blk = first_existing(s.g, *paths)
            if blk is None:
                counts[n] = None
                continue
            es = list(gs.iter_entries(s.g, *blk.body))
            es = [e for e in es if e.key and e.key.isdigit()]
            counts[n] = len(es)
            if sp == "none":
                tr[n] = sorted({depth0(s.g, e, field) for e in es})
                continue
            want = CSET[n] if sp == "char" else TSET[n]
            if n == "chain" and sp == "char":
                continue
            tr[n] = sum(1 for e in es if (v := depth0(s.g, e, field)) and v.isdigit() and int(v) in want)
        row(name, f"own id (by {field} -> {sp})", cons, counts, tr)
    # factions by county membership (title id)
    counts, tr = {}, {}
    for n, s in saves.items():
        es = [e for e in gs.iter_entries(s.g, *gs.locate(s.g, "faction_manager/factions").body) if e.key]
        counts[n] = len(es)
        tr[n] = sum(1 for e in es if any(int(v) in TSET[n] for v in depth0_all(s.g, e, "county")))
    row("faction_manager/factions [county members]", "own id (by title_members/county -> title)", "n", counts, tr)
    # memories: listed in the transplanted characters' alive_data/memories
    counts, tr = {}, {}
    for n, s in saves.items():
        mem = {i for i, _ in T.entries(s.g, "character_memory_manager/database")}
        counts[n] = len(mem)
        if n == "chain":
            continue
        want = CSET[n]
        listed = set()
        for p in ("living",):
            for i, e in T.entries(s.g, p):
                if i in want:
                    m = re.search(rb"\n\t+memories=\{([^}]*)\}", s.g[e.open:e.close])
                    if m:
                        listed |= {int(x) for x in m.group(1).split()}
        tr[n] = f"{len(listed & mem)}/{len(listed)} listed memories present"
    row("character_memory_manager/database", "own id (listed in alive_data/memories)", "y", counts, tr)
    # saints: character + province
    counts, tr = {}, {}
    for n, s in saves.items():
        try:
            b = gs.locate(s.g, "faiths/saints")
        except gs.GamestateError:
            counts[n] = None
            continue
        es = list(gs.iter_entries(s.g, *b.body))
        counts[n] = len(es)
        if n != "chain":
            tr[n] = sum(1 for e in es if (v := depth0(s.g, e, "character")) and int(v) in CSET[n])
            tr[n + "_prov"] = sum(1 for e in es if (v := depth0(s.g, e, "province")) and int(v) in tr_prov)
    row("faiths/saints", "anonymous (character, province)", "n", counts, tr)
    # important locations: county title id
    counts, tr = {}, {}
    for n, s in saves.items():
        try:
            b = gs.locate(s.g, "landed_titles/important_locations")
        except gs.GamestateError:
            counts[n] = None
            continue
        es = list(gs.iter_entries(s.g, *b.body))
        counts[n] = len(es)
        tr[n] = sum(1 for e in es if (v := depth0(s.g, e, "county")) and int(v) in TSET[n])
        if n == "ref":
            print("   important_locations counties:",
                  sorted({s.tkey.get(int(depth0(s.g, e, "county"))) for e in es})[:20])
    row("landed_titles/important_locations", "anonymous (county title id)", "n", counts, tr)
    # stories: which cycles belong to transplanted people
    cyc = Counter()
    for i, e in T.entries(R.g, "stories/active"):
        o = depth0(R.g, e, "owner")
        cyc[(depth0(R.g, e, "story_cycle"), int(o) in c_ref if o else None)] += 1
    print("   ref stories (cycle, owner transplanted):", dict(cyc))
    ia = Counter()
    for i, e in T.entries(R.g, "important_action_manager/active"):
        o = depth0(R.g, e, "character")
        ia[int(o) in c_ref if o else None] += 1
    print("   ref important actions by transplanted owner:", dict(ia))
    # pair lists and events
    for path, (fa, fb) in (("relations/active_relations", ("first", "second")),
                           ("opinions/active_opinions", ("owner", "target"))):
        counts, tr = {}, {}
        for n, s in saves.items():
            es = list(gs.iter_entries(s.g, *gs.locate(s.g, path).body))
            counts[n] = len(es)
            if n == "chain":
                continue
            w = CSET[n]
            both = one = 0
            for e in es:
                x, y = depth0(s.g, e, fa), depth0(s.g, e, fb)
                ix, iy = (int(x) in w) if x else False, (int(y) in w) if y else False
                both += ix and iy
                one += ix != iy
            tr[n] = {"both_transplanted": both, "one_side": one}
        row(path, "anonymous pair (character, character)", "y", counts, tr)
    counts = {n: sum(1 for _ in gs.find_sections(s.g, "triggered_event")) for n, s in saves.items()}
    row("triggered_event", "repeated top-level (typed scopes)", "y", counts, {})
    # provinces
    row("provinces", "province id", "y", {n: len(s.provinces) for n, s in saves.items()},
        {"ref_for_tr": len(tr_prov), "ours": len(tr_prov & O.provinces), "res": len(tr_prov & S.provinces),
         "chain": len(tr_prov & C.provinces)})
    row(TITLES, "own id (key= title key)", "y", {n: len(s.tkey) for n, s in saves.items()},
        {"ref_for_tr": len(tr_keys), "ours": len(tr_keys & O.tid.keys()), "res": len(tr_keys & S.tid.keys()),
         "chain": len(tr_keys & C.tid.keys())})
    Path(a[5]).write_text(json.dumps({"rows": rows, "title_base": tbase, "char_base": cbase,
                                      "transplanted": {"titles": len(tr_keys), "characters": len(c_ref),
                                                       "provinces": len(tr_prov)}}, indent=1), encoding="utf-8")
    print(f"done in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
