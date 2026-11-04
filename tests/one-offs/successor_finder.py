"""successor_finder: propose a 1.20 successor for each old key, matched on what the thing is (the culture goal's U2).

djdarcy (2026-11-04): "We may be able to look at similar metadata values to find something that became the new
teutonic knights in our saves." Names misled twice that night (teutonic_knights -> order_knights; scholar_perk ->
scholarly_circles_perk), so the name is only a tiebreaker:

  men-at-arms    same `type` (heavy_infantry ...), then the nearest (damage, toughness); class first: a type defined in
                 a cultural/accolade/regional file is only matched by one from the same kind of file
  perks          same lifestyle tree, same `position`, same `parent`
  modifiers      a known family rewrite (artifact_<x>_scheme_power_add_<n> -> artifact_<x>_scheme_phase_duration_add_<n>),
                 else the closest name among modifiers of the same file family
  innovations    the closest name among 1.20 innovations

Each row: old key, kind, proposed successor, how it was matched, confidence (clear / likely / unsure / none), and the
evidence (file and values). Old definitions come from the 1.8.2 game kept under private/data/versions/1.8.2/game/common,
new ones from the installed game. Read-only.

Usage: python -I tests/one-offs/successor_finder.py <kind>:<key> [...] [--json out.json]
  kinds: maa, perk, modifier, innovation
"""
from __future__ import annotations

import difflib
import glob
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OLD = REPO / "private" / "data" / "versions" / "1.8.2" / "game" / "common"
NEW = Path(r"E:\SteamLibrary\steamapps\common\Crusader Kings III\game\common")


def blocks(folder: Path) -> dict:
    """top-level `key = { ... }` blocks of every .txt in folder: key -> (body, file name)."""
    out = {}
    for f in sorted(glob.glob(str(folder / "*.txt"))):
        t = re.sub(r"#[^\n]*", "", Path(f).read_text(encoding="utf-8-sig", errors="replace"))
        for m in re.finditer(r"(?m)^([A-Za-z_0-9]+)\s*=\s*\{", t):
            # match the braces: a one-line `key = { a = 1 }` ends on its own line (searching for "\n}" ran on
            # into the following definitions, 2026-11-04)
            depth, i = 1, m.end()
            while depth and i < len(t):
                depth += {"{": 1, "}": -1}.get(t[i], 0)
                i += 1
            out[m.group(1)] = (t[m.end():i - 1], Path(f).name)
    return out


def num(body, key):
    m = re.search(rf"\b{key}\s*=\s*(-?[\d.]+)", body)
    return float(m.group(1)) if m else None


def word(body, key):
    m = re.search(rf"\b{key}\s*=\s*\{{?\s*([A-Za-z_0-9]+)", body)
    return m.group(1) if m else None


def maa_class(fname: str) -> str:
    for k in ("cultural", "accolade", "holy_order", "ep3", "regional"):
        if k in fname:
            return k
    return "generic"


def find_maa(key):
    old, new = blocks(OLD / "men_at_arms_types"), blocks(NEW / "men_at_arms_types")
    if key in new:
        return key, "same name", "clear", "defined in 1.20"
    if key not in old:
        return None, "not in 1.8.2", "none", ""
    ob, of = old[key]
    ty, d, t = word(ob, "type"), num(ob, "damage") or 0, num(ob, "toughness") or 0
    cls = maa_class(of)
    cands = []
    for k, (b, f) in new.items():
        if word(b, "type") != ty:
            continue
        dist = abs((num(b, "damage") or 0) - d) + abs((num(b, "toughness") or 0) - t)
        # a cultural unit is only replaced by a generic one of the same type: another culture's unit is not the
        # same troops (chu_ko_nu must not become archers_of_the_nile)
        if cls == "cultural" and maa_class(f) == "cultural":
            continue
        same_class = maa_class(f) == cls or (cls == "holy_order" and "holy" in f) or maa_class(f) == "generic"
        cands.append((not same_class, dist, k, f, num(b, "damage"), num(b, "toughness")))
    if not cands:
        return None, f"no 1.20 {ty}", "none", ""
    cands.sort()
    other_class, dist, k, f, nd, nt = cands[0]
    conf = "clear" if dist <= 4 and not other_class else ("likely" if dist <= 8 else "unsure")
    return k, f"type {ty}, nearest stats", conf, f"old {d:g}/{t:g} ({of}); new {nd:g}/{nt:g} ({f})"


def find_perk(key):
    old, new = blocks(OLD / "lifestyle_perks"), blocks(NEW / "lifestyle_perks")
    if key in new:
        return key, "same name", "clear", "defined in 1.20"
    if key not in old:
        return None, "not in 1.8.2", "none", ""
    ob, of = old[key]
    tree = word(ob, "tree")
    pos = re.search(r"position\s*=\s*\{\s*(\d+)\s+(\d+)\s*\}", ob)
    parents = set(re.findall(r"\bparent\s*=\s*([a-z_0-9]+)", ob))
    for k, (b, f) in new.items():
        p = re.search(r"position\s*=\s*\{\s*(\d+)\s+(\d+)\s*\}", b)
        if word(b, "tree") == tree and p and pos and p.groups() == pos.groups():
            same_parent = parents & set(re.findall(r"\bparent\s*=\s*([a-z_0-9]+)", b))
            return k, "same tree, position" + (" and parent" if same_parent else ""), \
                "clear" if same_parent else "likely", f"tree {tree} {pos.groups()} ({of} -> {f})"
    return None, f"no perk at {tree} {pos.groups() if pos else '?'}", "none", ""


def find_modifier(key):
    new = blocks(NEW / "modifiers")
    if key in new:
        return key, "same name", "clear", "defined in 1.20"
    m = re.match(r"artifact_([a-z_]+)_scheme_power_add_(\d+)_modifier$", key)
    if m:
        cand = f"artifact_{m.group(1)}_scheme_phase_duration_add_{m.group(2)}_modifier"
        if cand in new:
            return cand, "family rewrite (1.13 scheme rework: power -> phase duration), same scheme and tier", \
                "clear", new[cand][1]
    # the effect rule (djdarcy: "bring them back or the nearest thing to"): the same effect keys, nearest values
    old = blocks(OLD / "modifiers")
    if key in old:
        eff = dict((k, float(v)) for k, v in re.findall(r"\b([a-z_]+)\s*=\s*(-?[\d.]+)", old[key][0]))
        if eff:
            best = None
            # a modifier of a family (artifact_...) is matched within its family first: an artifact's bonus becoming
            # an event's modifier tells the player a wrong story (2026-11-04)
            fam = key.split("_")[0] + "_" if key.startswith("artifact_") else ""
            for k, (b, f) in new.items():
                ne = dict((a, float(v)) for a, v in re.findall(r"\b([a-z_]+)\s*=\s*(-?[\d.]+)", b))
                if set(ne) != set(eff) or any((ne[a] > 0) != (eff[a] > 0) for a in eff):
                    continue                    # a bonus never becomes a penalty, nor the reverse
                dist = (0 if k.startswith(fam) else 1000) + sum(abs(ne[a] - eff[a]) for a in eff)
                if best is None or dist < best[0]:
                    best = (dist, k, f, ne)
            if best and best[0] >= 1000:
                best = (best[0] - 1000, best[1], best[2] + ", outside its family", best[3])
            if best:
                conf = "likely" if best[0] == 0 else "unsure"
                return best[1], "same effects" + (" and values" if best[0] == 0 else ", nearest values"), conf, \
                    f"old {eff} ({old[key][1]}); new {best[3]} ({best[2]})"
            return None, f"no 1.20 modifier with the effects {sorted(eff)}", "none", f"old {eff} ({old[key][1]})"
    near = difflib.get_close_matches(key, list(new), n=1, cutoff=0.8)
    if near:
        return near[0], "closest name", "unsure", new[near[0]][1]
    return None, "no 1.20 modifier of that family or name (not in 1.8.2 common/modifiers either: event-local or a mod's)", \
        "none", ""


def find_innovation(key):
    """Same group and era, then a 1.20 innovation whose icon file carries the old name (1.20 kept
    innovation_bombards.dds as the icon of innovation_gunpowder), then the closest name in that group and era."""
    folder = NEW / "culture" / "innovations"
    new, old = blocks(folder), blocks(OLD / "culture" / "innovations")
    if key in new:
        return key, "same name", "clear", "defined in 1.20"
    if key not in old:
        return None, "not in 1.8.2", "none", ""
    ob, of = old[key]
    grp, era = word(ob, "group"), word(ob, "culture_era")
    same = {k: v for k, v in new.items() if word(v[0], "group") == grp and word(v[0], "culture_era") == era}
    icons = {}                                  # @var = "path" per file, to resolve `icon = @var`
    for f in glob.glob(str(folder / "*.txt")):
        for var, path in re.findall(r'(?m)^(@[a-z_0-9]+)\s*=\s*"([^"]+)"', Path(f).read_text(encoding="utf-8-sig",
                                                                                                errors="replace")):
            icons[var] = path
    for k, (b, f) in same.items():
        ic = re.search(r"\bicon\s*=\s*(@?[a-z_0-9]+)", b)
        path = icons.get(ic.group(1), ic.group(1)) if ic else ""
        if Path(path).stem.rstrip("s") == key.rstrip("s"):
            return k, "same group and era; its icon carries the old name", "likely", \
                f"{grp}, {era}; icon {Path(path).name} ({f})"
    near = difflib.get_close_matches(key, list(same), n=1, cutoff=0.6)
    if near:
        return near[0], "same group and era, closest name", "unsure", f"{grp}, {era} ({same[near[0]][1]})"
    return None, f"nothing in {grp}, {era}", "none", ""


FINDERS = {"maa": find_maa, "perk": find_perk, "modifier": find_modifier, "innovation": find_innovation}


def main():
    argv = sys.argv[1:]
    if "--json" in argv:                       # its value is a path, not a key
        del argv[argv.index("--json") + 1]
    args = [a for a in argv if not a.startswith("--")]
    rows = []
    for a in args:
        kind, key = a.split(":", 1)
        succ, how, conf, ev = FINDERS[kind](key)
        rows.append({"key": key, "kind": kind, "successor": succ, "how": how, "confidence": conf, "evidence": ev})
        print(f"{kind:10s} {key:52s} -> {str(succ):52s} [{conf}] {how}; {ev}")
    if "--json" in sys.argv:
        Path(sys.argv[sys.argv.index("--json") + 1]).write_text(json.dumps(rows, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
