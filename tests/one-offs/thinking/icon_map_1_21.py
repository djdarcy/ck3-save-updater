"""How far do the building icons take the S1 successor table? Three icon signals per 1.20 family, with tiers.

djdarcy 2026-11-19: "If we can find a common element like the same graphic then we know they're intended to be related
in some way. Can you create a tool to see how much that gives us in terms of mappings? Also obviously we want to match
the correct tiers from the old game to the new game where possible."

Signals, per 1.20 building family F (its icon is 1.20's type_icon, e.g. icon_building_guild_halls.dds; 1.21 still ships
that picture as gfx/.../building_types/old_buildings/guild_halls.dds):
  REUSE  a 1.21 building whose type_icon IS old_buildings/<F's icon>.dds  -- the very same picture, reused on purpose
  NAME   a 1.21 building whose icon file has the same stem in a NEW folder (regular_buildings/guild_halls.dds)
         -- same file name, which may be different art (guild halls: a gatehouse then, a shield with tools now)
  ART    the 1.21 icons whose silhouette is closest to F's old picture (alpha masks at 32x32, IoU); proposes only

For each candidate: the districts and holding types that host it, its chain length and the district level each tier
needs, beside F's own tier count and the tiers v17 actually holds. Weighted by v17's instances (the S1 table).

Also prints the structural comparison 1.20 vs 1.21 (chains, tiers, gates, trade-good needs) for the "how customizable
are buildings now" question.

Prediction (written first): REUSE + NAME together give a candidate for at most a third of the 66 families by count;
ART adds proposals but needs eyes; tiers line up 1:1 for few families because 1.21 gates tiers by district level.

Run: python -I -X utf8 tests/one-offs/thinking/icon_map_1_21.py <1.20 game dir> <1.21 game dir> <s1 json> <out.json> [sheet.png]
Reads only (plus the two outputs).
"""
import collections
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
from ck3_save_migrator import host_rules  # noqa: E402

ICON_DIR = pathlib.Path("gfx/interface/icons/building_types")


def fam(key):
    return re.sub(r"_\d+$", "", key)


def tier(key):
    m = re.search(r"_(\d+)$", key)
    return int(m.group(1)) if m else 0


def building_blocks(game):
    """key -> body text, every building in common/buildings (top-level `key = {` blocks)."""
    out = {}
    for f in sorted((pathlib.Path(game) / "common" / "buildings").rglob("*.txt")):
        for key, body, _ in host_rules._blocks(f):
            out[key] = body
    return out


def icon_of(body):
    m = re.search(r'\btype_icon\s*=\s*"?([^"\s]+)', body)
    return m.group(1) if m else None


def stem(path):
    s = pathlib.PurePosixPath(path).stem
    return re.sub(r"^icon_building_", "", s)


def masks(game, size=32):
    """'folder/stem' -> 32x32 alpha mask (tuple of bools), for every icon under building_types/."""
    from PIL import Image
    root = pathlib.Path(game) / ICON_DIR
    out = {}
    for p in sorted(root.rglob("*.dds")):
        try:
            im = Image.open(p).convert("RGBA").resize((size, size))
        except Exception:
            continue
        a = im.getchannel("A").tobytes()
        out[p.relative_to(root).with_suffix("").as_posix()] = tuple(v > 96 for v in a)
    return out


def iou(a, b):
    inter = sum(1 for x, y in zip(a, b) if x and y)
    union = sum(1 for x, y in zip(a, b) if x or y)
    return inter / union if union else 0.0


def main(old_game, new_game, s1_json, out_json, sheet=None):
    old_b, new_b = building_blocks(old_game), building_blocks(new_game)
    rules = host_rules.load(new_game)

    # 1.21: building family -> icon ('folder/stem'), tiers, level requirements, hosting districts and holdings
    new_icon, new_chain = {}, collections.defaultdict(list)
    for k, body in new_b.items():
        ic = icon_of(body)
        if ic and fam(k) not in new_icon:
            new_icon[fam(k)] = pathlib.PurePosixPath(ic).with_suffix("").as_posix()
        new_chain[fam(k)].append(k)
    host = collections.defaultdict(set)   # building family -> {(district, holding)}
    for h, (names, _) in rules.holdings.items():
        for d in names:
            dist = rules.districts.get(d)
            if dist:
                for b in dist.buildings:
                    host[fam(b)].add((d, h))
    by_icon = collections.defaultdict(set)
    for f, ic in new_icon.items():
        by_icon[ic].add(f)

    # 1.20: family -> icon stem, tier count
    old_icon, old_tiers = {}, collections.Counter()
    for k, body in old_b.items():
        old_tiers[fam(k)] = max(old_tiers[fam(k)], tier(k))
        ic = icon_of(body)
        if ic and fam(k) not in old_icon:
            old_icon[fam(k)] = stem(ic)

    # v17 usage from the S1 table (regular families only)
    s1 = json.loads(pathlib.Path(s1_json).read_text(encoding="utf-8"))
    use, held, kind = collections.Counter(), collections.defaultdict(collections.Counter), {}
    for r in s1:
        if r["kind"] in ("holding line", "wonder"):
            continue
        use[r["family"]] += r["instances"]
        kind[r["family"]] = r["kind"]
        for k, n in r.get("keys", {}).items():
            held[r["family"]][tier(k)] += n

    mk = masks(new_game) if sheet is not None or True else {}

    def describe(f):
        tiers = sorted(new_chain[f], key=tier)
        lv = [rules.level_req.get(k) for k in tiers]
        return {"family": f, "icon": new_icon.get(f), "tiers": len(tiers),
                "level_req": lv, "hosts": sorted({d for d, _ in host[f]})[:6],
                "holdings": sorted({h for _, h in host[f]})}

    rows = []
    for f in sorted(use, key=lambda x: -use[x]):
        st = old_icon.get(f)
        reuse = sorted(by_icon.get(f"old_buildings/{st}", ())) if st else []
        name = sorted(g for ic, fs in by_icon.items() if st and ic.split("/")[-1] == st
                      and not ic.startswith("old_buildings/") for g in fs)
        art = []
        old_mask = mk.get(f"old_buildings/{st}") if st else None
        if old_mask:
            scored = []
            for ic, m in mk.items():
                if ic.startswith("old_buildings/") or ic not in by_icon:
                    continue
                scored.append((iou(old_mask, m), ic))
            scored.sort(reverse=True)
            art = [(round(s, 2), ic, sorted(by_icon[ic])) for s, ic in scored[:3]]
        same = sorted(d for d in reuse) + sorted(
            g for g in name if old_mask and new_icon.get(g) in mk and iou(old_mask, mk[new_icon[g]]) >= 0.9)
        rows.append({
            "family": f, "v17": use[f], "s1_kind": kind[f], "old_icon": st, "old_tiers": old_tiers.get(f, 0),
            "same_picture": same,
            "v17_tiers": dict(sorted(held[f].items())),
            "reuse": [describe(g) for g in reuse], "name": [describe(g) for g in name],
            "art": [{"iou": s, "icon": ic, "families": fs} for s, ic, fs in art],
        })

    # summary
    total = sum(use.values())
    def cov(pred):
        fs = [r for r in rows if pred(r)]
        return len(fs), sum(r["v17"] for r in fs)
    for label, pred in (("REUSE (same picture)", lambda r: r["reuse"]),
                        ("NAME only (same file name, new folder)", lambda r: r["name"] and not r["reuse"]),
                        ("REUSE or NAME", lambda r: r["reuse"] or r["name"]),
                        ("SAME PICTURE (reuse, or name with iou>=0.9)", lambda r: r["same_picture"]),
                        ("  ... with exactly one same-picture building", lambda r: len(r["same_picture"]) == 1),
                        ("ART >= 0.6 (close silhouette)", lambda r: r["art"] and r["art"][0]["iou"] >= 0.6),
                        ("no old icon file found", lambda r: not r["old_icon"])):
        n, w = cov(pred)
        print(f"{label:42s} {n:3d} of {len(rows)} families, {w:6d} of {total} v17 buildings ({100 * w / total:.0f}%)")
    print()
    print("family | v17 | 1.20 tiers (v17 holds) | REUSE | NAME | ART top (iou)")
    for r in rows:
        fmt = lambda xs: ", ".join(f"{d['family']}[{d['tiers']}t lv{d['level_req'][:4]}]" for d in xs) or "-"
        a = r["art"][0] if r["art"] else None
        print(f"{r['family']} | {r['v17']} | {r['old_tiers']} ({r['v17_tiers']}) | {fmt(r['reuse'])} | {fmt(r['name'])} | "
              + (f"{'/'.join(a['families'])} ({a['iou']})" if a else "-"))

    # structure: 1.20 vs 1.21
    def chains(blocks, rx):
        c = collections.Counter()
        for k in blocks:
            if re.search(rx, k):
                c[fam(k)] += 1
        return c
    oc = chains(old_b, r"_\d+$")
    nc = chains(new_b, r"_\d+$")
    need = sum(1 for b in new_b.values() if "trade_good_need" in b)
    lvl = sum(1 for b in new_b.values() if "district_level_requirement" in b)
    print(f"\nstructure: 1.20 {len(oc)} tiered families, {sum(oc.values())} building keys, mean {sum(oc.values()) / len(oc):.1f} tiers;"
          f" 1.21 {len(nc)} tiered families, {sum(nc.values())} keys, mean {sum(nc.values()) / len(nc):.1f} tiers;"
          f" 1.21 keys with a trade-good need {need}, with a district-level requirement {lvl};"
          f" 1.21 districts {len(rules.districts)}")
    pathlib.Path(out_json).write_text(json.dumps(rows, indent=1), encoding="utf-8")

    if sheet:
        from PIL import Image, ImageDraw
        root = pathlib.Path(new_game) / ICON_DIR
        top = [r for r in rows if r["old_icon"]][:24]
        W = Image.new("RGBA", (64 * 5 + 230, 64 * len(top)), (60, 60, 60, 255))
        dr = ImageDraw.Draw(W)
        for i, r in enumerate(top):
            dr.text((2, 64 * i + 4), f"{r['family'][:28]}\nv17 {r['v17']}", fill=(255, 255, 255, 255))
            icons = [f"old_buildings/{r['old_icon']}"]
            icons += [d["icon"] for d in r["reuse"][:1] + r["name"][:1]]
            icons += [a["icon"] for a in r["art"][:3]]
            for j, ic in enumerate(icons[:5]):
                p = root / (ic + ".dds")
                if p.exists():
                    im = Image.open(p).convert("RGBA").resize((60, 60))
                    W.alpha_composite(im, (230 + 64 * j, 64 * i + 2))
        W.save(sheet)


if __name__ == "__main__":
    main(*sys.argv[1:])
