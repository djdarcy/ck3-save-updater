"""#6 criterion 2: "Every county that exists only on the new map carries the holder (and that holder's dynasty,
court and liege chain) the reference gives it". For each county key the old save lacks, compares the holder in the
updated save with the reference's, by identity (first name and birth date; the transplant renumbers ids), and the
holder's liege's identity the same way. Counties the report settles on the campaign (R17 "settled") are listed apart.
Known answer: the reference itself, compared with itself, matches on every county.
Usage: python -I newmap_county_holders.py <old gamestate (extracted)> <updated .ck3> <reference .ck3> [report.json]"""
import json
import re
import sys
from collections import Counter

sys.path.insert(0, r"C:\code\ck3-save-migrator")
from ck3_save_migrator import savefile as sf, gamestate as gs  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def load(p):
    try:
        return sf.read_save(p).gamestate
    except Exception:
        return open(p, "rb").read()


def titles(d):
    """{key: (holder, de_facto_liege title id)}, and {title id: key}."""
    b = gs.locate(d, "landed_titles/landed_titles")
    out, by_id = {}, {}
    for e in gs.iter_entries(d, *b.body):
        body = d[e.open:e.close]
        k = re.search(rb'(?m)^\tkey="?([\w-]+)', body)
        if not k:
            continue
        key = k.group(1).decode()
        h = re.search(rb"(?m)^\tholder=(\d+)", body)
        lg = re.search(rb"(?m)^\tde_facto_liege=(\d+)", body)
        out[key] = (h.group(1).decode() if h else None, lg.group(1).decode() if lg else None)
        by_id[e.key.decode()] = key
    return out, by_id


def people(d):
    """{character id: (first_name, birth)} over living."""
    lv = gs.find_section(d, "living")
    seg = d[lv.start:lv.end]
    out = {}
    for m in re.finditer(rb"(?m)^(\d+)=\{\n\tfirst_name=\"?([^\"\n]*)\"?\n(?:\t[^\n]*\n)*?\tbirth=([\d.]+)", seg):
        out[m.group(1).decode()] = (m.group(2).decode(), m.group(3).decode())
    return out


def view(d):
    t, by_id = titles(d)
    pp = people(d)
    return {k: (pp.get(h) if h else None, by_id.get(lg)) for k, (h, lg) in t.items() if k.startswith("c_")}


def main():
    old_keys = set(titles(load(sys.argv[1]))[0])
    new, ref = view(load(sys.argv[2])), view(load(sys.argv[3]))
    settled = set()
    if len(sys.argv) > 4:
        rep = json.load(open(sys.argv[4], encoding="utf-8"))
        for r in rep["rules"]:
            if r["id"] == "R17":
                settled = {row["new county"] for row in r["extra"].get("settled", [])}
    only_new = sorted(k for k in ref if k not in old_keys)
    res = Counter()
    bad = []
    for k in only_new:
        if k in settled:
            res["settled on the campaign (report)"] += 1
        elif k not in new:
            res["missing from the updated save"] += 1
            bad.append((k, "missing"))
        elif new[k][0] != ref[k][0]:
            res["holder differs"] += 1
            bad.append((k, f"holder {new[k][0]} vs reference {ref[k][0]}"))
        elif new[k][1] != ref[k][1]:
            res["liege title differs"] += 1
            bad.append((k, f"liege title {new[k][1]} vs reference {ref[k][1]}"))
        else:
            res["same holder and liege title"] += 1
    print(f"new-map counties: {len(only_new)}; " + ", ".join(f"{n} {w}" for w, n in res.most_common()))
    for k, why in bad[:15]:
        print("  ", k, why)


if __name__ == "__main__":
    main()
