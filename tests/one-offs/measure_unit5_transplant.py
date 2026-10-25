"""Unit 5 measurement 2: what transplanting 1.20's new regions from a reference save involves.

For the 1.8.1 save and the 1.20 reference: the id spaces (characters, titles, dynasties, houses, cultures,
provinces) and whether they collide; the titles new in 1.20 and who holds them in the reference; the closure of
reference characters behind those titles (holders, their courts, their close family), with the dynasties,
houses and cultures that closure uses; and which top-level sections reference provinces, titles or characters.

Usage: python -I tests/one-offs/measure_unit5_transplant.py <old gamestate> <1.20 reference gamestate>
"""
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator import lint as L  # noqa: E402

COL0 = re.compile(rb"(?m)^(\d+)=\{")


def ids_col0(g, idx, path):
    b = idx.block(path)
    return [int(m.group(1)) for m in COL0.finditer(g, b.open, b.close)] if b else []


def ids_entries(g, idx, path):
    b = idx.block(path)
    return [int(e.key) for e in gs.iter_entries(g, *b.body) if e.key.isdigit()] if b else []


def summary(label, g):
    idx = L.SectionIndex(g)
    chars = {s: ids_col0(g, idx, s) for s in ("living", "dead_unprunable", "characters/dead_prunable")}
    out = {
        "characters": sorted(i for v in chars.values() for i in v),
        "titles": ids_col0(g, idx, "landed_titles/landed_titles"),
        "houses": ids_col0(g, idx, "dynasties/dynasty_house"),
        "dynasties": ids_col0(g, idx, "dynasties/dynasties"),
        "cultures": ids_entries(g, idx, "culture_manager/cultures"),
        "provinces": ids_entries(g, idx, "provinces"),
    }
    print(f"== {label}")
    for k, v in out.items():
        if v:
            print(f"  {k:10} {len(v):>8,} ids, min {min(v):>10,} max {max(v):>12,}")
    return idx, out


def titles(g, idx):
    lt = idx.block("landed_titles/landed_titles")
    out = {}
    for t in gs.iter_entries(g, *lt.body):
        body = g[t.open:t.close]
        k = re.search(rb'\n\tkey="?([\w\-\']+)', body)
        if not k:
            continue
        h = re.search(rb"\n\tholder=(\d+)", body)
        out[k.group(1).decode()] = (int(t.key), int(h.group(1)) if h else None)
    return out


def char_links(g, idx):
    """character id -> (employer, family ids, house, culture)"""
    out = {}
    for sec in ("living",):
        b = idx.block(sec)
        starts = [(int(m.group(1)), m.start()) for m in COL0.finditer(g, b.open, b.close)]
        for n, (cid, st) in enumerate(starts):
            end = starts[n + 1][1] if n + 1 < len(starts) else b.close
            body = g[st:end]
            emp = re.search(rb"\n\t\temployer=(\d+)", body)
            fam = [int(x) for x in re.findall(rb"\n\t\t(?:spouse|primary_spouse|real_father)=(\d+)", body)]
            for lst in re.findall(rb"\n\t\t(?:child)=\{([^}]*)\}", body):
                fam += [int(x) for x in lst.split()]
            house = re.search(rb"\n\tdynasty_house=(\d+)", body)
            cul = re.search(rb"\n\tculture=(\d+)", body)
            out[cid] = (int(emp.group(1)) if emp else None, fam,
                        int(house.group(1)) if house else None, int(cul.group(1)) if cul else None)
    return out


def main():
    old = Path(sys.argv[1]).read_bytes()
    ref = Path(sys.argv[2]).read_bytes()
    oidx, o = summary("1.8.1 save", old)
    ridx, r = summary("1.20 reference", ref)
    print("== id collisions (same number used in both)")
    for k in ("characters", "titles", "houses", "dynasties", "cultures"):
        print(f"  {k:10} {len(set(o[k]) & set(r[k])):>8,} shared numbers")

    ot, rt = titles(old, oidx), titles(ref, ridx)
    new = {k: v for k, v in rt.items() if k not in ot and not k.startswith("x_")}
    held = {k: v for k, v in new.items() if v[1] is not None}
    print(f"== titles new in 1.20: {len(new):,}; held in the reference: {len(held):,} "
          f"by {len({v[1] for v in held.values()}):,} characters; by tier {dict(Counter(k[:2] for k in held))}")

    links = char_links(ref, ridx)
    holders = {v[1] for v in held.values()}
    court = {c for c, (emp, _, _, _) in links.items() if emp in holders}
    family = {f for h in holders if h in links for f in links[h][1]}
    closure = holders | court | family
    living = set(links)
    print(f"== closure in the reference: holders {len(holders):,}, their courts {len(court):,}, "
          f"close family {len(family):,}; union {len(closure):,} ({len(closure & living):,} living)")
    houses = Counter(links[c][2] for c in closure if c in links and links[c][2] is not None)
    cultures = Counter(links[c][3] for c in closure if c in links and links[c][3] is not None)
    print(f"  houses used {len(houses):,}; cultures used {len(cultures):,}")
    # cultures the closure uses, by template, and whether the old save has that template
    cm = ridx.block("culture_manager/cultures")
    tmpl = {int(e.key): (re.search(rb'culture_template="?([\w\-]+)', ref[e.open:e.close]) or [None, b"?"])[1].decode()
            for e in gs.iter_entries(ref, *cm.body)}
    ocm = oidx.block("culture_manager/cultures")
    old_tmpl = set(re.findall(rb'[\n\t]culture_template="?([\w\-]+)', old[ocm.open:ocm.close]))
    missing = sorted({tmpl.get(c, "?") for c in cultures if tmpl.get(c, "?").encode() not in old_tmpl})
    print(f"  cultures the closure uses that the old save lacks: {len(missing)}: {missing}")

    # which fields in which sections hold a closure character id (numbers can coincide with other ids, so this
    # over-counts for fields that hold other kinds of numbers; the field names say which ones are characters)
    secs0 = [(m.group(1).decode(), m.start()) for m in re.finditer(rb"(?m)^([a-z_]+)=\{", ref)]
    st0 = [s for _, s in secs0]
    import bisect as _b
    refs = Counter()
    for m in re.finditer(rb"([A-Za-z_]\w*)[ \t]*=[ \t]*(?:(\d+)\b|\{([\d\s]*)\})", ref):
        field = m.group(1).decode()
        vals = [int(m.group(2))] if m.group(2) else [int(x) for x in m.group(3).split()]
        n = sum(1 for v in vals if v in closure)
        if n:
            refs[(secs0[_b.bisect_right(st0, m.start()) - 1][0], field)] += n
    print("== where closure character ids appear in the reference (section, field): top 40")
    for (sec, field), n in refs.most_common(40):
        print(f"  {n:>7,}  {sec:28} {field}")

    # faiths the closure follows (through its rites); the save already carries 1.20's faith database (R8)
    rites = {int(e.key): ref[e.open:e.close] for e in gs.iter_entries(ref, *ridx.block("rites/database").body)}
    faiths = {int(e.key): ref[e.open:e.close] for e in gs.iter_entries(ref, *ridx.block("faiths/database").body)}
    lv = ridx.block("living")
    starts = [(int(m.group(1)), m.start()) for m in COL0.finditer(ref, lv.open, lv.close)]
    rite_of = {}
    for n, (cid, st) in enumerate(starts):
        if cid in closure:
            end = starts[n + 1][1] if n + 1 < len(starts) else lv.close
            m = re.search(rb"\n\trite=(\d+)", ref[st:end])
            if m:
                rite_of[cid] = int(m.group(1))
    def faith_tag(fid):
        m = re.search(rb'tag="([^"]+)"', faiths.get(fid, b""))
        return m.group(1).decode() if m else str(fid)
    by_faith = Counter()
    for cid, rid in rite_of.items():
        fm = re.search(rb"[\n\t]faith=(\d+)", rites.get(rid, b""))
        by_faith[faith_tag(int(fm.group(1))) if fm else "?"] += 1
    print(f"== faiths of the closure's living characters ({sum(by_faith.values()):,} with a rite): "
          f"{len(by_faith)} faiths; top {by_faith.most_common(12)}")

    # de jure seams: parents by KEY (ids differ between the saves)
    def parents(g, idx, key_of):
        lt = idx.block("landed_titles/landed_titles")
        out = {}
        for t in gs.iter_entries(g, *lt.body):
            body = g[t.open:t.close]
            k = re.search(rb'\n\tkey="?([\w\-\']+)', body)
            dj = re.search(rb"\n\tde_jure_liege=(\d+)", body)
            if k:
                out[k.group(1).decode()] = key_of.get(int(dj.group(1))) if dj else None
        return out
    okey = {v[0]: k for k, v in ot.items()}
    rkey = {v[0]: k for k, v in rt.items()}
    op, rp = parents(old, oidx, okey), parents(ref, ridx, rkey)
    shared = [k for k in op if k in rp and not k.startswith("x_")]
    moved = [(k, op[k], rp[k]) for k in shared if op[k] != rp[k]]
    print(f"== de jure parents of titles in both: {len(shared):,}; different in 1.20: {len(moved):,}; "
          f"by tier {dict(Counter(k[:2] for k, _, _ in moved))}")
    print(f"  e.g. {moved[:12]}")
    seam = Counter(rp[k] for k in new if rp.get(k) in ot)
    print(f"== new 1.20 titles whose de jure parent exists in the old save: {sum(seam.values()):,} under "
          f"{len(seam):,} parents; e.g. {seam.most_common(10)}")

    print("== top-level sections in the reference that mention a new-region province id (> 9,659), sampled")
    hits = Counter()
    secs = [(m.group(1).decode(), m.start()) for m in re.finditer(rb"(?m)^([a-z_]+)=\{", ref)]
    starts = [s for _, s in secs]
    import bisect
    for m in re.finditer(rb"(?:location|province|capital_province|origin|county_capital)=(\d{4,5})\b", ref):
        if int(m.group(1)) > 9659:
            hits[secs[bisect.bisect_right(starts, m.start()) - 1][0]] += 1
    print(f"  {dict(hits.most_common(15))}")


if __name__ == "__main__":
    main()
