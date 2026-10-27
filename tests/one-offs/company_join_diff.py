"""company_join_diff: every carried mercenary company, joined out to its title, captain, regiments and home county,
compared with its twin in the 1.20 reference (djdarcy 2026-10-27: "look at the full joins across a working company
from a real game versus ours to see what differs").

Pairs are found through the company's title: our title id = reference title id + the title offset (the transplant's
translation, measured from title keys by shape_diff.keys). Each joined record is reduced to field -> value with ids
mapped back where the space is known (titles, characters, companies, regiments by offset), and every difference is
counted across all pairs by (record kind, field, kind of difference), with examples. A difference shared by every
pair is the systemic one.

Usage: python -I tests/one-offs/company_join_diff.py <ours.ck3> <reference.ck3> <engine chain.ck3> [--examples N]
"""
from __future__ import annotations

import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import shape_diff as P  # noqa: E402
from ck3_save_migrator import gamestate as gs  # noqa: E402

LOW, GEN = 0xFFFFFF, 0xFF000000


def db(g: bytes, path: str) -> dict[int, bytes]:
    try:
        b = gs.locate(g, path)
    except gs.GamestateError:
        return {}
    return {int(e.key): g[e.start:e.end] for e in gs.iter_entries(g, *b.body) if e.key and e.key.isdigit()}


def fields(body: bytes, depth: bytes = b"\t") -> dict[str, str]:
    """field -> raw value text for the entry's direct scalar fields and small blocks (one level)."""
    out = {}
    for m in re.finditer(rb"\n" + depth + rb"([a-z_]+)=(\{[^{}]*\}|\"[^\"]*\"|[^\s{]+)", body):
        out.setdefault(m.group(1).decode(), m.group(2).decode("utf-8", "replace").replace("\n", " ").replace("\t", ""))
    return out


def landed(body: bytes) -> dict[str, str]:
    m = re.search(rb"\n\tlanded_data=\{", body)
    if not m:
        return {}
    end = gs.match_brace(body, m.end() - 1)
    return {f"landed.{k}": v for k, v in fields(body[m.end():end], b"\t\t").items()}


def main():
    ours_p, ref_p, chain_p = sys.argv[1:4]
    n_ex = int(sys.argv[sys.argv.index("--examples") + 1]) if "--examples" in sys.argv else 4
    G = {"ours": P.load(ours_p), "ref": P.load(ref_p)}
    # keys() finds the campaign's characters as those ours shares with the engine's own conversion (chain)
    K = P.keys({"ref": G["ref"], "chain": P.load(chain_p), "ours": G["ours"]})
    toff, coff = K.title_offset, K.char_offset
    tr_t = lambda i: (i & GEN) | ((i & LOW) + toff)            # noqa: E731
    tr_c = lambda i: (i & GEN) | ((i & LOW) + coff)            # noqa: E731
    comp = {s: db(G[s], "mercenary_company_manager/mercenary_companies") for s in G}
    titles = {s: db(G[s], "landed_titles/landed_titles") for s in G}
    living = {s: db(G[s], "living") for s in G}
    regs = {s: db(G[s], "armies/regiments") for s in G}
    county = {s: db(G[s], "county_manager/counties") for s in G}       # keyed by title key, not id: unused
    by_title = {s: {int(re.search(rb"\n\t+title=(\d+)", b).group(1)): c for c, b in comp[s].items()
                    if re.search(rb"\n\t+title=(\d+)", b)} for s in G}
    pairs = [(rc, by_title["ours"][tr_t(rt)], rt) for rt, rc in by_title["ref"].items() if tr_t(rt) in by_title["ours"]]
    print(f"title offset {toff}, character offset {coff}; companies ours {len(comp['ours'])}, ref {len(comp['ref'])}; "
          f"carried pairs {len(pairs)}")
    diffs = Counter()
    ex = defaultdict(list)

    def compare(kind, a: dict, b: dict, idmap: dict, tag: str):
        for k in sorted(set(a) | set(b)):
            va, vb = a.get(k), b.get(k)
            if va is None or vb is None:
                key = (kind, k, "only in ref" if vb is None else "only in ours")
            else:
                fa = idmap.get(k, lambda v: v)(va)
                if fa == vb:
                    continue
                key = (kind, k, "value differs")
            diffs[key] += 1
            if len(ex[key]) < n_ex:
                ex[key].append(f"{tag}: ref {va!s:.70} | ours {vb!s:.70}")

    num = lambda f: (lambda v: str(f(int(v))) if v.isdigit() else v)      # noqa: E731
    for rc, oc, rt in pairs:
        ot = tr_t(rt)
        rcf, ocf = fields(comp["ref"][rc], b"\t\t\t"), fields(comp["ours"][oc], b"\t\t\t")
        compare("company", rcf, ocf, {"title": num(tr_t), "county": num(tr_t)}, f"company {rc}->{oc}")
        rtf, otf = fields(titles["ref"][rt]), fields(titles["ours"][ot])
        for k in ("key", "coat_of_arms_id", "history", "title_name_data", "color"):
            rtf.pop(k, None), otf.pop(k, None)
        compare("title", rtf, otf, {"holder": num(tr_c), "capital": num(tr_t), "mercenary": lambda v: v},
                f"title {rt}->{ot}")
        rh = rtf.get("holder")
        if rh and rh.isdigit():
            rch, och = living["ref"].get(int(rh)), living["ours"].get(tr_c(int(rh)))
            if rch is None or och is None:
                diffs[("captain", "entry", "missing in " + ("ref" if rch is None else "ours"))] += 1
            else:
                a, b = landed(rch), landed(och)
                a.update({f"court.{k}": v for k, v in fields(rch, b"\t\t").items() if k in ("employer", "host")})
                b.update({f"court.{k}": v for k, v in fields(och, b"\t\t").items() if k in ("employer", "host")})
                compare("captain", a, b, {"landed.realm_capital": num(tr_t), "court.employer": num(tr_c),
                                          "court.host": num(tr_c)}, f"captain {rh}->{tr_c(int(rh))}")
        rr = re.search(rb"regiments=\{([^}]*)\}", comp["ref"][rc])
        orr = re.search(rb"regiments=\{([^}]*)\}", comp["ours"][oc])
        rl = [int(x) for x in rr.group(1).split()] if rr else []
        ol = [int(x) for x in orr.group(1).split()] if orr else []
        if len(rl) != len(ol):
            diffs[("regiments", "count", "differs")] += 1
        for a, b in zip(rl, ol):
            ra, ob = regs["ref"].get(a), regs["ours"].get(b)
            if ra is None or ob is None:
                diffs[("regiment", "entry", "missing in " + ("ref" if ra is None else "ours"))] += 1
                continue
            compare("regiment", fields(ra, b"\t\t\t"), fields(ob, b"\t\t\t"), {"owner": num(tr_c)}, f"regiment {a}->{b}")
    print(f"differences across {len(pairs)} pairs (kind, field, how): count")
    for key, n in diffs.most_common():
        print(f"  {key[0]:9} {key[1]:28} {key[2]:15} {n:4}   e.g. {ex[key][0] if ex[key] else ''}")


if __name__ == "__main__":
    main()
