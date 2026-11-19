"""Generate the first ck3_save_migrator/successors/successors_1_21.toml from the S1 table (built-state carry, step 5).

After this one run the TOML is maintained by hand (djdarcy's answers to the HOLD list go into it), so this script is a
record of where the first version came from, not a build step.

Rules (the collabN-local 1 final assessment, 2026-11-19 13:49):
- one entry per 1.20 regular building family, keyed by family; `successors` is an ORDERED list of alternatives, each
  {building (the family's 1.21 line), district}; host_rules decides per holding which one is legal there, so a row
  needs no holding-type key;
- settled rows from S1 go in, except the three icon rows the review sent back (borghi, village hunter, turbary);
- every other family is `open`, with the reason, so the carry names it at run time instead of skipping it silently;
- families from the 1.20 game files that v17 does not hold are listed too (the review's finding 6c).

Run: python -I -X utf8 tests/one-offs/thinking/make_successor_table.py <s1 table.json> <1.20 game dir> <out.toml>
"""
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
from ck3_save_migrator.host_rules import _blocks  # noqa: E402

BACK_TO_OPEN = {"hill_farms", "hunting_grounds", "peat_quarries"}   # culture/terrain-locked successors (the review)
NOT_REGULAR = ("00_duchy_capital", "00_legendary", "00_special", "ccp3_special", "cp6_special", "cp8_special",
               "tgp_great_project", "99_", "_buildings.info", "00_nomad", "00_admin")
HOLDING_LINES = {"castle", "city", "temple", "tribe", "nomadic_camp", "herder_camp", "temple_citadel"}


def fam(k):
    return re.sub(r"_\d+$", "", k)


def main(table, old_game, out):
    rows = json.loads(pathlib.Path(table).read_text(encoding="utf-8"))
    by_fam = {}
    for r in rows:
        if r["kind"] in ("holding line", "wonder"):
            continue
        e = by_fam.setdefault(r["family"], {"instances": 0, "succ": None, "source": None})
        e["instances"] += r["instances"]
        if r["kind"] == "settled" and r["family"] not in BACK_TO_OPEN:
            e["succ"], e["source"] = (fam(r["successor"]), r["district"]), r["source"]
    old = set()
    for f in sorted((pathlib.Path(old_game) / "common" / "buildings").glob("*.txt")):
        if f.name.startswith(NOT_REGULAR):
            continue
        for key, body, _ in _blocks(f):
            if re.search(r"_\d+$", key) and fam(key) not in HOLDING_LINES:
                old.add(fam(key))
    lines = ["# What each 1.20 regular building becomes in 1.21: the built-state carry's successor table.",
             "# Maintained by hand. First generated 2026-11-19 by tests/one-offs/thinking/make_successor_table.py from the",
             "# S1 table (private vault: notes/testing/2026-11-19__03-10-00__s1-successor-table.json).",
             "#",
             "# successors: an ORDERED list of alternatives; the carry takes the first that host_rules finds legal on the",
             "#   holding (district enabled there, prerequisite present, tier within the district's level, the county's",
             "#   trade-good potential). An empty list, or `open`, means the family is not carried and is named in the report.",
             "# source: same (the key survives), icon (a 1.21 building drawn with the old icon), djdarcy (his answer, dated).",
             ""]
    for f in sorted(set(by_fam) | old):
        e = by_fam.get(f)
        lines.append(f"[families.{f}]")
        if e and e["succ"]:
            b, d = e["succ"]
            lines.append(f'successors = [{{ building = "{b}", district = "{d}", source = "{e["source"]}" }}]')
        else:
            why = ("open: djdarcy's answer pending (HOLD 2026-11-19, the S1 list)" if e else
                   "open: not held in the founding campaign; no successor chosen yet")
            lines.append("successors = []")
            lines.append(f'open = "{why}"')
        if e:
            lines.append(f"seen = {e['instances']}   # instances in the founding campaign (v17)")
        lines.append("")
    pathlib.Path(out).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(out).write_text("\n".join(lines), encoding="utf-8")
    settled = sum(1 for f in by_fam if by_fam[f]["succ"])
    print(f"families: {len(set(by_fam) | old)} ({len(by_fam)} seen in v17, {len(old - set(by_fam))} only in the 1.20 "
          f"files); settled {settled}")


if __name__ == "__main__":
    main(*sys.argv[1:4])
