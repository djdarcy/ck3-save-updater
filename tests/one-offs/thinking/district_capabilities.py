"""Who may build each 1.21 district type, read from its own definition -- not inferred from where it sits at game start.

The mistake this checks for (2026-11-19): "resource districts are game-assigned" was inferred from the start state
(history/provinces places them at 867/1066) and stated as a capability. The definition said otherwise:
`can_construct_potential = { county = { has_potential_for_trade_good = ... } }`, `can_be_replaced = yes`. The pattern:
an observation of the starting state used as a rule about construction. This probe reads every district's own fields
so each label rests on its definition.

Per district type (common/districts/*.txt): its file, `type`, whether it has can_construct_potential / is_enabled /
can_be_replaced / show_disabled, and the gate's atoms (trade-good potential, government flags, titles, terrain, holy
sites, scripted triggers named). Summary per file.

Run: python -I -X utf8 tests/one-offs/thinking/district_capabilities.py <1.21 game dir> [<out.json>]
Read-only (plus the optional JSON).
"""
import collections
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
from ck3_save_migrator import host_rules  # noqa: E402

ATOMS = [
    ("trade-good potential", r"has_potential_for_trade_good"),
    ("government", r"government_has_flag|_government_trigger"),
    ("duchy title", r"can_have_duchy_capital_building_trigger|has_title"),
    ("terrain", r"\bterrain\b|is_coastal|is_riverside"),
    ("holy site", r"holy_site|is_holy_site"),
    ("county capital", r"is_county_capital"),
    ("culture/faith", r"has_cultural_parameter|culture|faith|religion"),
    ("great project / legend", r"great_project|legend"),
    ("trade system", r"trade_post|entrepot|is_trade|market"),
]


def inner(body, key):
    m = re.search(r"\b" + key + r"\s*=\s*\{", body)
    if not m:
        return None
    depth, i = 1, m.end()
    while i < len(body) and depth:
        depth += {"{": 1, "}": -1}.get(body[i], 0)
        i += 1
    return body[m.end():i - 1]


def main(game, out=None):
    rows = []
    for f in sorted((pathlib.Path(game) / "common" / "districts").glob("*.txt")):
        for k, body, _ in host_rules._blocks(f):
            ccp, ena = inner(body, "can_construct_potential"), inner(body, "is_enabled")
            gate = (ccp or "") + " " + (ena or "")
            t = re.search(r"\btype\s*=\s*(\w+)", body)
            rows.append({"district": k, "file": f.stem, "type": t.group(1) if t else None,
                         "can_construct_potential": ccp is not None, "is_enabled": ena is not None,
                         "can_be_replaced": bool(re.search(r"\bcan_be_replaced\s*=\s*yes", body)),
                         "show_disabled": bool(re.search(r"\bshow_disabled\s*=\s*yes", body)),
                         "gate": [a for a, rx in ATOMS if re.search(rx, gate)],
                         "triggers": sorted(set(re.findall(r"\b(\w+_trigger)\b", gate)))[:6]})
    by = collections.defaultdict(list)
    for r in rows:
        by[r["file"]].append(r)
    print("file | types | with can_construct_potential | with is_enabled | can_be_replaced | gates seen")
    for fn, rs in by.items():
        gates = collections.Counter(a for r in rs for a in r["gate"])
        print(f"{fn} | {len(rs)} | {sum(r['can_construct_potential'] for r in rs)} | {sum(r['is_enabled'] for r in rs)} | "
              f"{sum(r['can_be_replaced'] for r in rs)} | {dict(gates.most_common(5))}")
    for fn in ("special_mines_districts", "great_districts", "trade_post_districts", "entrepot_districts",
               "legendary_districts", "other_special_districts"):
        ex = [r for r in by.get(fn, [])][:2]
        for r in ex:
            print(f"  e.g. {r['district']}: ccp={r['can_construct_potential']} enabled={r['is_enabled']} "
                  f"replace={r['can_be_replaced']} gate={r['gate']} triggers={r['triggers']}")
    if out:
        pathlib.Path(out).write_text(json.dumps(rows, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main(*sys.argv[1:])
