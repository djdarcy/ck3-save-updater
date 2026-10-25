"""Unit 2 proof-of-concept: transplant one ruler's realm from the 1.20 reference into a migrated save, through R13.

Arm A (designed to pass): the realm (every title de facto under the ruler), its holders, their courtiers, their
close family (one hop, living and dead), and the objects those people and titles need: houses, dynasties,
cultures (template not in the save), coats of arms, council tasks, court positions, vassal contracts, memories,
artifacts, ai strategies, the realm's province entries and their regiments. Ids go through translate.Translator;
a reference to anything not in the output is removed (the edge policy), so no translated id dangles.

Arm B (the control, designed to fail): the same with --no-offset -- joins still apply, the per-space offset does
not, so reference ids land on the save's own ids.

Usage:
  python -I tests/one-offs/poc_transplant.py <migrated save .ck3> <reference .ck3> --ruler <ref char id>
         -o <out.ck3> [--no-offset] [--report <report.json>]
"""
import argparse
import json
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator import idschema as S  # noqa: E402
from ck3_save_migrator import savefile as sf  # noqa: E402
from ck3_save_migrator import translate as T  # noqa: E402

GAME = Path(r"E:\SteamLibrary\steamapps\common\Crusader Kings III\game")
FAMILY = ("family_data/spouse", "family_data/primary_spouse", "family_data/former_spouses/*",
          "family_data/child/*", "family_data/betrothed", "family_data/concubine", "family_data/concubinist",
          "family_data/former_concubines/*", "family_data/former_concubinists/*", "family_data/real_father")
# per-character objects carried with a transplanted person: (space, the reference database kind)
CARRIED = {
    "house": "dynasties/dynasty_house", "dynasty": "dynasties/dynasties", "culture": "culture_manager/cultures",
    "council_task": "council_task_manager/active", "court_position": "court_positions/database",
    "vassal_contract": "vassal_contracts/database", "memory": "character_memory_manager/database",
    "artifact": "artifacts/artifacts", "coat_of_arms": "coat_of_arms/coat_of_arms_manager_database",
    "regiment": "armies/regiments",
}
# where each reference kind goes in the save (a 1.8.1-shaped save keeps contracts in vassal_contracts/active)
TARGET = {"vassal_contracts/database": "vassal_contracts/active"}


def barony_provinces() -> dict[str, int]:
    out, cur = {}, None
    for f in (GAME / "common" / "landed_titles").glob("*.txt"):
        t = f.read_text(encoding="utf-8-sig", errors="replace")
        for m in re.finditer(r"\b(b_[\w\-']+)\s*=\s*\{|\bprovince\s*=\s*(\d+)", t):
            if m.group(1):
                cur = m.group(1)
            elif cur:
                out[cur] = int(m.group(2))
                cur = None
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("save")
    ap.add_argument("ref")
    ap.add_argument("--ruler", type=int, required=True)
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--no-offset", action="store_true")
    ap.add_argument("--report")
    a = ap.parse_args()
    t0 = time.time()
    save = sf.read_save(a.save)
    S_g = save.gamestate
    R_g = sf.read_save(a.ref).gamestate
    tr = T.Translator.build(S_g, R_g)
    if a.no_offset:
        for m in tr.spaces.values():
            m.base = 0
    log = {"arm": "B (no offset)" if a.no_offset else "A", "ruler": a.ruler}
    print(f"translator {time.time() - t0:.0f}s")

    # -- reference indexes --------------------------------------------------
    ent = {}                                     # (space-kind, id) -> entry block
    for kind in ["living", "dead_unprunable", "landed_titles/landed_titles", "provinces", "ai/ai_strategies",
                 *CARRIED.values()]:
        ent[kind] = dict(T.entries(R_g, kind))
    chars = {**{i: ("dead_unprunable", e) for i, e in ent["dead_unprunable"].items()},
             **{i: ("living", e) for i, e in ent["living"].items()}}
    refs = {}

    def refs_of(kind, i, e):
        k = (kind, i)
        if k not in refs:
            refs[k] = list(T.references(R_g, e, kind))
        return refs[k]

    titles = ent["landed_titles/landed_titles"]
    holder, dfl, key = {}, {}, {}
    for i, e in titles.items():
        b = R_g[e.open:min(e.close, e.open + 2000)]
        m = re.search(rb"\n\tholder=(\d+)", b)
        holder[i] = int(m.group(1)) if m else None
        m = re.search(rb"\n\tde_facto_liege=(\d+)", b)
        dfl[i] = int(m.group(1)) if m else None
        k = T._depth0(R_g, e, T._KEY)
        key[i] = k.decode() if k else "?"
    held = defaultdict(list)
    sub = defaultdict(list)
    for i in titles:
        if holder[i] is not None:
            held[holder[i]].append(i)
        if dfl[i] is not None:
            sub[dfl[i]].append(i)

    # -- the realm and the people --------------------------------------------
    realm, todo = set(), list(held[a.ruler])
    while todo:
        t = todo.pop()
        if t in realm:
            continue
        realm.add(t)
        todo += sub[t]
        if holder[t] is not None:
            todo += [x for x in held[holder[t]] if x not in realm]
    joined_c = tr.spaces["character"].join
    holders = {holder[t] for t in realm if holder[t] is not None}
    employer = defaultdict(list)
    parents = defaultdict(list)
    for i, (kind, e) in chars.items():
        for path, sp, v in refs_of(kind, i, e):
            if path == "court_data/employer":
                employer[v].append(i)
            elif path == "family_data/child/*":
                parents[v].append(i)
    courtiers = {c for h in holders for c in employer[h]}
    core = holders | courtiers
    family = set()
    for x in core:
        kind, e = chars[x]
        family |= {v for path, sp, v in refs_of(kind, x, e) if path in FAMILY}
        family |= set(parents[x])
    people = {p for p in core | family if p in chars}
    excluded_joined = {p for p in people if p in joined_c}
    people -= excluded_joined
    log.update(realm_titles=len(realm), holders=len(holders), courtiers=len(courtiers - holders),
               family_added=len(family - core), people=len(people), excluded_history_joined=len(excluded_joined),
               living=sum(1 for p in people if chars[p][0] == "living"),
               dead=sum(1 for p in people if chars[p][0] == "dead_unprunable"))

    # -- the objects they carry (to a fixpoint) ------------------------------
    carry = defaultdict(set)                     # space -> reference ids to transplant
    carry["character"] = set(people)
    carry["title"] = {t for t in realm if t not in tr.spaces["title"].join}
    bp = barony_provinces()
    save_prov = {i for i, _ in T.entries(S_g, "provinces")}
    provs = {bp[key[t]] for t in realm if key[t] in bp}
    carry["province"] = {p for p in provs if p in ent["provinces"] and p not in save_prov}
    carry["ai"] = {p for p in people if p in ent["ai/ai_strategies"]}
    log["provinces_in_realm"] = len(provs)
    log["provinces_already_in_save"] = len(provs & save_prov)
    frontier = [("character", p) for p in people] + [("title", t) for t in carry["title"]] + \
               [("province", p) for p in carry["province"]]
    kind_of = {"character": None, "title": "landed_titles/landed_titles", "province": "provinces", **CARRIED}
    while frontier:
        sp, i = frontier.pop()
        kind, e = chars[i] if sp == "character" else (kind_of[sp], ent[kind_of[sp]][i])
        for path, rsp, v in refs_of(kind, i, e):
            if rsp not in CARRIED or v in carry[rsp] or v in tr.spaces[rsp].join:
                continue
            if rsp in ("house", "dynasty", "culture", "coat_of_arms", "regiment") or sp == "character":
                if v in ent[CARRIED[rsp]]:
                    carry[rsp].add(v)
                    frontier.append((rsp, v))

    # a title of the realm the campaign already has (b_wuyuan in the d_shuofang realm) stays the campaign's:
    # the transplanted people and titles drop their references to it rather than claim it
    realm_joined = {t for t in realm if t in tr.spaces["title"].join}
    log["realm_titles_kept_by_campaign"] = sorted(key[t] for t in realm_joined)

    def keep(space, v, path=""):
        m = tr.spaces[space]
        if space in S.IDENTITY:
            return True
        if space == "title" and v in realm_joined:
            return False
        if v in m.join:
            return v not in m.join_pruned
        return v in carry[space]

    # -- rewrite and insert --------------------------------------------------
    rep = T.RewriteReport()
    ep = gs.EditPass()
    blocks = {}

    def target(kind):
        k = TARGET.get(kind, kind)
        if k not in blocks:
            blocks[k] = gs.locate(S_g, k)
        return blocks[k]

    payload = defaultdict(list)
    for p in sorted(people):
        kind, e = chars[p]
        payload[kind].append(T.rewrite_entry(R_g, e, kind, tr, rep, keep))
    for p in sorted(carry["ai"]):
        payload["ai/ai_strategies"].append(T.rewrite_entry(R_g, ent["ai/ai_strategies"][p], "ai/ai_strategies",
                                                           tr, rep, keep))
    for t in sorted(carry["title"]):
        payload["landed_titles/landed_titles"].append(
            T.rewrite_entry(R_g, titles[t], "landed_titles/landed_titles", tr, rep, keep))
    for pv in sorted(carry["province"]):
        payload["provinces"].append(T.rewrite_entry(R_g, ent["provinces"][pv], "provinces", tr, rep, keep))
    for sp, kind in CARRIED.items():
        for i in sorted(carry[sp]):
            payload[kind].append(T.rewrite_entry(R_g, ent[kind][i], kind, tr, rep, keep))
    counts = {}
    for kind, items in payload.items():
        # at the start of the closing brace's line, so every inserted entry starts at column 0 as the game
        # writes them (a nested section closes with "\t}"; inserting at the brace put the first entry after
        # the tab, where column-0 readers -- lint, our probes -- did not see it)
        blk = target(kind)
        at = S_g.rfind(b"\n", 0, blk.close) + 1
        ep.add(gs.Edit(at, at, b"".join(x + b"\n" for x in items), "POC", kind))
        counts[TARGET.get(kind, kind)] = len(items)
    log["inserted"] = counts

    # counters, lookups
    coa = gs.locate(S_g, "coat_of_arms")
    nxt = T._depth0_scalars(S_g, coa, "next_id")[-1]
    new_next = tr.coa_next_id([tr.spaces["coat_of_arms"].translate(i) for i in carry["coat_of_arms"]])
    ep.add(gs.Edit(nxt.value_start, nxt.value_end, str(new_next).encode(), "POC", "coat next_id"))
    tl = gs.find_section(S_g, "traits_lookup")
    if tr.new_traits:
        ep.insert(tl, "end", (" ".join(tr.new_traits) + " ").encode(), "POC", "traits")
    rl = T.character_lookup(R_g)
    adds = [f"\t{h}={tr.spaces['character'].translate(c)}\n" for h, c in sorted(rl.items()) if c in people]
    if adds:
        ep.insert(gs.find_section(S_g, "character_lookup"), "end", "".join(adds).encode(), "POC", "lookup")
    log.update(coa_next_id=[tr.save_coa_next_id, new_next], traits_appended=len(tr.new_traits),
               character_lookup_added=len(adds))
    ep.apply_to(save)
    sf.write_save(save, a.out, force=True)
    log["dropped_references"] = {f"{k} | {p}": n for (k, p), n in rep.dropped.most_common(40)}
    log["dropped_total"] = sum(rep.dropped.values())
    log["translated"] = dict(rep.translated)
    log["unlisted"] = {f"{k} | {p}": n for (k, p), n in rep.unlisted.items()}
    log["seconds"] = round(time.time() - t0)
    print(json.dumps({k: v for k, v in log.items() if k != "dropped_references"}, indent=1))
    print("dropped (top):", list(log["dropped_references"].items())[:15])
    if a.report:
        Path(a.report).write_text(json.dumps(log, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
