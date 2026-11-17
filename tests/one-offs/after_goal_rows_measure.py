"""MEASURE: the after-goal pass -- the ten field rows lint still reports, and carried faiths' empty doctrine groups.

For each (database, field) row: how many of v16's entries lack it; whether those same entries carried it in the
original 1.8.1 save (lost by the update) or never had it (a field the game added, or a 1.8 state); and what the game
writes for that field in its own fresh 1.20 save (values and how often), so the design can choose between deriving a
value, copying the original, or a measured allow-list. Then, for every faith in v16, the choosable doctrine groups it
has nothing in. Read-only. Run:
python -I -X utf8 tests/one-offs/after_goal_rows_measure.py <v16.ck3> <original_1_8_1.ck3> <ref_1_20.ck3> <game_dir>
"""
import collections
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from ck3_save_migrator import faith_rules  # noqa: E402
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator.savefile import read_save  # noqa: E402

ROWS = [("artifacts/artifacts", f) for f in ("type", "modifiers", "wealth", "quality")] + [
    ("culture_manager/cultures", "head_determination"), ("culture_manager/cultures", "culture_template"),
    ("coat_of_arms/coat_of_arms_manager_database", "colored_emblem"),
    ("landed_titles/landed_titles", "coat_of_arms_id"), ("tax_slot_manager/tax_slots", "tax_collector")]


def table(g, path):
    try:
        b = gs.locate(g, path)
    except gs.GamestateError:
        return {}
    out = {}
    for e in gs.iter_entries(g, b.open + 1, b.close):
        if e.key and e.key.isdigit():
            f = {}
            for c in gs.iter_children(g, e.open + 1, e.close):
                if c.key:
                    f.setdefault(c.key.decode(), g[c.value_start:c.value_end].strip())
            out[e.key.decode()] = f
    return out


def filled(v):
    return v is not None and v.strip(b'{} \t\r\n"') != b""


def main(v16, orig, ref, game):
    G = {n: read_save(p).gamestate for n, p in (("v16", v16), ("orig", orig), ("ref", ref))}
    for path, field in ROWS:
        T = {n: table(g, path) for n, g in G.items()}
        if not T["v16"]:
            print(f"\n{path}: not found in v16 (path to check)")
            continue
        lack = [k for k, f in T["v16"].items() if not filled(f.get(field))]
        in_orig = [k for k in lack if k in T["orig"]]
        orig_had = [k for k in in_orig if filled(T["orig"][k].get(field))]
        ref_vals = collections.Counter(T["ref"][k].get(field, b"<absent>")[:40] for k in T["ref"])
        print(f"\n{path} . {field}: v16 lacks {len(lack)} of {len(T['v16'])}; of those, {len(in_orig)} exist in the 1.8.1 "
              f"save with the same id, {len(orig_had)} had it filled there (orig has {len(T['orig'])} entries)")
        print(f"  ref ({len(T['ref'])} entries) values: {ref_vals.most_common(5)}")
        if lack:
            k = lack[0]
            print(f"  e.g. v16 {k}: keys {sorted(T['v16'][k])[:12]}")
            if k in T["orig"]:
                print(f"       orig {k}: {field}={T['orig'][k].get(field, b'<absent>')[:60]!r}")
    # living 45243
    lv = table(G["v16"], "living").get("45243", {})
    print(f"\nliving 45243: alive_data {'present' if 'alive_data' in lv else 'absent'}; dead_data "
          f"{'present' if 'dead_data' in lv else 'absent'}; keys {sorted(lv)[:14]}")
    # empty choosable doctrine groups per faith
    rules = faith_rules.load(game)
    groups = {g for g in rules.group_category if rules.group_must_be_filled(g)}
    fdb = table(G["v16"], "faiths/database")
    body = G["v16"]
    db = gs.locate(body, "faiths/database")
    per = {}
    for e in gs.iter_entries(body, db.open + 1, db.close):
        keys = set(m.decode() for m in re.findall(rb"(?m)^\t\t\tdoctrine=(\S+)", body[e.open:e.close]))
        have = {rules.doctrines[k].group for k in keys if k in rules.doctrines}
        per[e.key.decode()] = sorted(groups - have)
    counts = collections.Counter(len(v) for v in per.values())
    print(f"\nfaiths {len(per)}; choosable groups {len(groups)}; faiths by number of empty choosable groups: "
          f"{sorted(counts.items())}")
    for fid, empty in sorted(per.items(), key=lambda kv: -len(kv[1]))[:6]:
        tag = fdb.get(fid, {}).get("tag", b"")
        print(f"  faith {fid} {tag.decode(errors='replace')}: {len(empty)} empty: {empty}")
    common = collections.Counter(g for v in per.values() for g in v)
    print(f"  groups most often empty: {common.most_common(10)}")


if __name__ == "__main__":
    main(*sys.argv[1:5])
