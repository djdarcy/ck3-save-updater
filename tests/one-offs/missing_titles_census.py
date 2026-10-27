"""missing_titles_census: every title the 1.20 game defines that a migrated save lacks, measured per title.

2026-10-27: EPE's 99 "has_primary_title ... was null" errors are title:h_roman_empire not resolving: the migrated save
lacks titles a fresh 1.20 game has. The transplant (R14) leaves "unheld landless titles" to the engine (director,
2026-10-25 ~10:45, EXCLUSIONS row 14), on the claim that the engine creates them. This measures, per title:

- reference state: holder, de jure liege (and whether that key is in ours), de jure children, capital, coat of arms,
  name data, the top-level fields present, holy-order and mercenary links;
- engine-created: present by key in the game's own later saves of the migrated campaign;
- script references: `title:<key>` in vanilla 1.20 and in each installed mod given;
- conflicts: the key is a rename target or source in R15's report, a de jure liege missing from ours.

Known-answer cases (asserted): h_roman_empire is in the set, in the reference, named by vanilla; d_knights_hospitaller
is in the set and engine-created; c_roma is not in the set (it is in both saves).

Usage: python -I tests/one-offs/missing_titles_census.py <ours.ck3> <reference.ck3> <report.json> <out.tsv>
       [--later <game save of ours>]... [--mod <mod folder>]...
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator import savefile as sf  # noqa: E402

GAME = Path(r"E:\SteamLibrary\steamapps\common\Crusader Kings III\game")
KEY = re.compile(rb'\n\tkey="?([^"\s]+)"?')
TITLE_DEF = re.compile(r"(?<![\w.])([hekdcb]_[\w\-']+)\s*=\s*\{")
TITLE_REF = re.compile(r"title:([hekdcb]_[\w\-']+)")


def load(path: str) -> bytes:
    raw = Path(path).read_bytes()
    if raw[:3] == b"SAV" and raw[5:7] == b"00":
        return raw[raw.index(b"\n") + 1:]
    return sf.read_save(path).gamestate


def titles(g: bytes) -> tuple[dict[int, dict], dict[str, dict]]:
    lt = gs.locate(g, "landed_titles/landed_titles")
    byid, bykey = {}, {}
    for e in gs.iter_entries(g, *lt.body):
        if not (e.key and e.key.isdigit()):
            continue
        t = g[e.open:e.close]
        m = KEY.search(t)
        if not m:
            continue
        top = set(re.findall(rb"\n\t([a-z_]+)=", t))
        f = lambda k: (x.group(1).decode() if (x := re.search(rb"\n\t" + k + rb"=(\S+)", t)) else None)
        rec = {"id": int(e.key), "key": m.group(1).decode(), "holder": f(b"holder"), "dj": f(b"de_jure_liege"),
               "capital": f(b"capital"), "coa": f(b"coat_of_arms_id"), "fields": sorted(x.decode() for x in top)}
        byid[rec["id"]] = rec
        bykey[rec["key"]] = rec
    return byid, bykey


def script_refs(root: Path, wanted: set[str]) -> Counter:
    c = Counter()
    for sub in ("common", "events", "gfx", "gui"):
        d = root / sub
        if not d.exists():
            continue
        for f in d.rglob("*.txt"):
            if "landed_titles" in f.parts:
                continue
            for m in TITLE_REF.finditer(f.read_text(encoding="utf-8-sig", errors="replace")):
                if m.group(1) in wanted:
                    c[m.group(1)] += 1
    return c


def main():
    args = sys.argv[1:]
    later = [args[i + 1] for i, a in enumerate(args) if a == "--later"]
    mods = [Path(args[i + 1]) for i, a in enumerate(args) if a == "--mod"]
    ours_p, ref_p, report_p, out_p = [a for i, a in enumerate(args) if a not in ("--later", "--mod")
                                      and (i == 0 or args[i - 1] not in ("--later", "--mod"))][:4]
    defined = set()
    for f in (GAME / "common" / "landed_titles").glob("*.txt"):
        defined |= set(TITLE_DEF.findall(f.read_text(encoding="utf-8-sig", errors="replace")))
    g, r = load(ours_p), load(ref_p)
    oid, ok = titles(g)
    rid, rk = titles(r)
    missing = sorted(k for k in defined if k not in ok)
    in_ref = [k for k in missing if k in rk]
    not_in_ref = [k for k in missing if k not in rk]
    later_keys = []
    for p in later:
        _, lk = titles(load(p))
        later_keys.append((p, set(lk)))
    vanilla = script_refs(GAME, set(missing))
    mod_refs = {m.name: script_refs(m, set(missing)) for m in mods}
    children = Counter()
    for rec in rid.values():
        if rec["dj"] and rec["dj"].isdigit() and int(rec["dj"]) in rid:
            children[rid[int(rec["dj"])]["key"]] += 1
    rep = json.loads(Path(report_p).read_text(encoding="utf-8", errors="replace"))
    renames = set()
    for rule in rep.get("rules", []):
        ex = rule.get("extra") or {}
        for k in ("renamed", "removed"):
            v = ex.get(k)
            if isinstance(v, dict):
                renames |= set(v) | {x for x in v.values() if isinstance(x, str)}
            elif isinstance(v, list):
                renames |= {x for x in v if isinstance(x, str)}
    holy = re.findall(rb"title=(\d+)", r[gs.locate(r, "holy_orders/holy_orders").open:gs.locate(r, "holy_orders/holy_orders").close]) \
        if b"holy_orders=" in r else []
    holy_keys = {rid[int(x)]["key"] for x in holy if int(x) in rid}
    rows = []
    for k in in_ref:
        rec = rk[k]
        dj = rid[int(rec["dj"])]["key"] if rec["dj"] and rec["dj"].isdigit() and int(rec["dj"]) in rid else None
        cap = rid[int(rec["capital"])]["key"] if rec["capital"] and rec["capital"].isdigit() and int(rec["capital"]) in rid else None
        rows.append({
            "key": k, "tier": k[0], "held_in_ref": bool(rec["holder"]), "dj_liege": dj,
            "dj_liege_in_ours": (dj in ok) if dj else None, "dj_children": children[k],
            "capital": cap, "capital_in_ours": (cap in ok) if cap else None, "coa": bool(rec["coa"]),
            "holy_order_in_ref": k in holy_keys, "mercenary_field": "mercenary" in rec["fields"],
            "engine_created": [k in ks for _, ks in later_keys], "vanilla_refs": vanilla[k],
            "mod_refs": {n: c[k] for n, c in mod_refs.items() if c[k]}, "in_r15_report": k in renames,
            "fields": rec["fields"]})
    # known-answer cases
    assert "h_roman_empire" in in_ref and vanilla["h_roman_empire"] > 0, "known answer: h_roman_empire"
    hosp = next((x for x in rows if x["key"] == "d_knights_hospitaller"), None)
    assert hosp is not None and all(hosp["engine_created"]), "known answer: d_knights_hospitaller engine-created"
    assert "c_roma" not in missing and "c_roma" in ok and "c_roma" in rk, "known answer: c_roma in both"
    with open(out_p, "w", encoding="utf-8") as f:
        cols = ["key", "tier", "held_in_ref", "dj_liege", "dj_liege_in_ours", "dj_children", "capital",
                "capital_in_ours", "coa", "holy_order_in_ref", "mercenary_field", "engine_created", "vanilla_refs",
                "mod_refs", "in_r15_report", "fields"]
        f.write("\t".join(cols) + "\n")
        for x in rows:
            f.write("\t".join(str(x[c]) for c in cols) + "\n")
    # summary, reconciled
    n = len
    print(f"defined by 1.20: {n(defined)} = in ours {n(defined) - n(missing)} + missing {n(missing)}")
    print(f"missing {n(missing)} = in the fresh game {n(in_ref)} + not in the fresh game {n(not_in_ref)}")
    created = [x for x in rows if any(x["engine_created"])]
    print(f"of the {n(in_ref)}: engine-created in a later save {n(created)} {[x['key'] for x in created]}; "
          f"never created {n(in_ref) - n(created)}")
    print("by tier:", dict(Counter(x["tier"] for x in rows)))
    print("held in the fresh game:", sum(x["held_in_ref"] for x in rows), "| with de jure children:",
          sum(1 for x in rows if x["dj_children"]))
    lj = Counter((x["dj_liege"] is not None, x["dj_liege_in_ours"]) for x in rows)
    print("de jure liege: none", lj[(False, None)], "| in ours", lj[(True, True)], "| missing from ours",
          lj[(True, False)], [x["key"] + "->" + x["dj_liege"] for x in rows if x["dj_liege_in_ours"] is False][:8])
    cp = Counter((x["capital"] is not None, x["capital_in_ours"]) for x in rows)
    print("capital: none", cp[(False, None)], "| in ours", cp[(True, True)], "| missing from ours", cp[(True, False)])
    print("coat of arms:", sum(x["coa"] for x in rows), "| holy order in ref:", sum(x["holy_order_in_ref"] for x in rows),
          "| mercenary field:", sum(x["mercenary_field"] for x in rows), "| in R15's report:",
          sum(x["in_r15_report"] for x in rows))
    named = [x for x in rows if x["vanilla_refs"] or x["mod_refs"]]
    print(f"named by scripts: {n(named)} (vanilla {sum(1 for x in rows if x['vanilla_refs'])}, "
          f"refs {sum(x['vanilla_refs'] for x in rows)}; mods: "
          f"{ {m: sum(1 for x in rows if m in x['mod_refs']) for m in mod_refs} }) | named by none: {n(rows) - n(named)}")
    fields = Counter(f for x in rows for f in x["fields"])
    print("top-level fields among them:", fields.most_common(14))
    print("not in the fresh game (17 expected):", not_in_ref)
    print(f"wrote {out_p}")


if __name__ == "__main__":
    main()
