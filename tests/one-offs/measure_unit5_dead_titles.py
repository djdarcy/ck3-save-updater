"""Unit 5: the titles 1.20 no longer defines -- who holds them in the old save, what hangs off them, and
whether 1.20 has an obvious successor (decides "drop" or "map" for the dead-title list).

Successors:
  barony   -> the 1.20 barony on the same province (old province from an older vanilla landed_titles copy)
  county   -> the 1.20 county(ies) its baronies' successors belong to
  d/k/e    -> the 1.20 parent(s) of its de jure children's successors, one tier up
Also: an exact key in 1.20 under a different tier/prefix (e.g. k_x -> e_x) is reported.

Usage: python -I tests/one-offs/measure_unit5_dead_titles.py <old gamestate> <old vanilla 00_landed_titles.txt>
       <1.20 game/common/landed_titles folder>
"""
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator import lint as L  # noqa: E402

TOK = re.compile(r'"[^"]*"|[{}=]|[^\s{}="]+')
TITLE = re.compile(r"^[hekdcb]_")


def title_tree(paths):
    """key -> (parent key or None, province or None) from landed_titles files (nested blocks)."""
    parent, prov = {}, {}
    for p in paths:
        text = re.sub(r"#[^\n]*", "", Path(p).read_bytes().removeprefix(b"\xef\xbb\xbf").decode("utf-8", "replace"))
        toks = TOK.findall(text)
        stack = []          # (key or None) per open brace
        i = 0
        while i < len(toks):
            t = toks[i]
            if t == "{":
                stack.append(None)
            elif t == "}":
                if stack:
                    stack.pop()
            elif i + 2 < len(toks) and toks[i + 1] == "=" and toks[i + 2] == "{" and TITLE.match(t):
                titles = [k for k in stack if k]
                parent[t] = titles[-1] if titles else None
                stack.append(t)
                i += 3
                continue
            elif t == "province" and i + 2 < len(toks) and toks[i + 1] == "=":
                titles = [k for k in stack if k]
                if titles and titles[-1].startswith("b_"):
                    prov[titles[-1]] = int(toks[i + 2])
            i += 1
    return parent, prov


def main():
    g = Path(sys.argv[1]).read_bytes()
    old_parent, old_prov = title_tree([sys.argv[2]])
    new_paths = sorted(Path(sys.argv[3]).glob("*.txt"))
    new_parent, new_prov = title_tree(new_paths)
    prov_to_new_barony = {v: k for k, v in new_prov.items()}
    defined, conv = L.defined_title_keys(Path(sys.argv[3]).parent.parent)

    idx = L.SectionIndex(g)
    lt = idx.block("landed_titles/landed_titles")
    info, key_of = {}, {}
    for t in gs.iter_entries(g, *lt.body):
        body = g[t.open:t.close]
        k = re.search(rb'\n\tkey="?([\w\-\']+)', body)
        if not k:
            continue
        key = k.group(1).decode()
        key_of[t.key.decode()] = key
        get = lambda f: (lambda m: m.group(1).decode() if m else None)(re.search(rb"\n\t" + f + rb"=(\d+)", body))
        info[key] = {"id": t.key.decode(), "holder": get(b"holder"), "dj": get(b"de_jure_liege"), "df": get(b"de_facto_liege")}
    for v in info.values():
        v["dj"] = key_of.get(v["dj"]) if v["dj"] else None
        v["df"] = key_of.get(v["df"]) if v["df"] else None
    lv = idx.block("living")
    living = {int(m.group(1)) for m in re.compile(rb"(?m)^(\d+)=\{").finditer(g, lv.open, lv.close)}
    names = {}
    for m in re.compile(rb'(?m)^(\d+)=\{\n\tfirst_name="([^"]*)"').finditer(g, lv.open, lv.close):
        names[m.group(1).decode()] = m.group(2).decode("utf-8", "replace")

    dead = sorted(k for k in info if not k.startswith("x_") and k not in defined and k not in conv)
    children = defaultdict(list)             # de jure children in the old save
    for k, v in info.items():
        if v["dj"]:
            children[v["dj"]].append(k)
    vassals = Counter(v["df"] for v in info.values() if v["df"])

    def barony_successor(b):
        p = old_prov.get(b)
        return (prov_to_new_barony.get(p), p)

    def successors(k):
        """1.20 titles that take over k's land, one tier up from its leaves."""
        if k.startswith("b_"):
            s, _ = barony_successor(k)
            return Counter([s] if s else [])
        out = Counter()
        kids = children.get(k) or [c for c, par in old_parent.items() if par == k]
        for c in kids:
            for s, n in successors(c).items():
                up = new_parent.get(s) if s else None
                out[up] += n
        return out

    print(f"dead titles (key not defined by 1.20, not dynamic, not converted): {len(dead)}; "
          f"by tier {dict(Counter(k[:2] for k in dead))}")
    rows = []
    for k in dead:
        v = info[k]
        h = v["holder"]
        held = f"{h} {names.get(h, '')}".strip() + (" (living)" if h and int(h) in living else (" (not living)" if h else ""))
        same_key = [p + k[1:] for p in "hekdcb" if p + k[1:] in defined and p + k[1:] != k]
        if k.startswith("b_"):
            s, p = barony_successor(k)
            succ = f"province {p} -> {s}" if p else "no old province known"
        else:
            sc = successors(k)
            succ = ", ".join(f"{s}x{n}" for s, n in sc.most_common(3)) if sc else "none found"
        rows.append((k, held or "-", v["dj"] or "-", len(children.get(k, [])), vassals.get(k, 0), succ, same_key))
    for r in rows:
        print(f"{r[0]:28} holder {r[1]:34} dj {r[2]:22} dj-children {r[3]:>3} df-vassals {r[4]:>3} | {r[5]}"
              + (f" | same key in 1.20: {r[6]}" if r[6] else ""))
    # collision volume: successors of living-held dead titles that the 1.20 reference already gives a holder
    if len(sys.argv) > 4:
        ref = Path(sys.argv[4]).read_bytes()
        ridx = L.SectionIndex(ref)
        rlt = ridx.block("landed_titles/landed_titles")
        ref_holder = {}
        for t in gs.iter_entries(ref, *rlt.body):
            body = ref[t.open:t.close]
            k2 = re.search(rb'\n\tkey="?([\w\-\']+)', body)
            h2 = re.search(rb"\n\tholder=(\d+)", body)
            if k2 and h2:
                ref_holder[k2.group(1).decode()] = h2.group(1).decode()
        pairs, ref_people, unheld = [], set(), 0
        for k in dead:
            h = info[k]["holder"]
            if not (h and int(h) in living):
                continue
            succ = [barony_successor(k)[0]] if k.startswith("b_") else [s for s, _ in successors(k).most_common()]
            for s in succ:
                if not s:
                    continue
                if s in ref_holder:
                    pairs.append((k, s, ref_holder[s]))
                    ref_people.add(ref_holder[s])
                else:
                    unheld += 1
        print(f"\ncollisions: {len(pairs)} successor titles of living-held dead titles are held in the reference, "
              f"by {len(ref_people)} distinct reference characters; {unheld} successors unheld there; "
              f"by tier {dict(Counter(s[:2] for _, s, _ in pairs))}")
    held_living = sum(1 for k in dead if info[k]["holder"] and int(info[k]["holder"]) in living)
    with_succ = sum(1 for r in rows if "->" in r[5] and not r[5].endswith("-> None") or (not r[0].startswith("b_") and r[5] != "none found"))
    print(f"\nheld by a living character: {held_living} of {len(dead)}; with a successor found: {with_succ}")


if __name__ == "__main__":
    main()
