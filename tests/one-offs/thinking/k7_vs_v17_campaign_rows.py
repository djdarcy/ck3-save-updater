"""Does the 1.8 -> 1.21 route (K7: to_1_20 fed a 1.21 reference) reproduce v17 (to_1_20 fed a 1.20 reference) on the
campaign's own rows? (djdarcy 2026-11-18 ~21:55: "Have we been able to reproduce the v17 golden using 1.21 (Florin)
and our original 1.8 savegame")

For each database, the entries whose id exists in the original 1.8.1 save (the campaign's own rows; reference-copied
rows are left out by construction) are compared byte for byte between the K7 chain and v17. Differing entries are
grouped by the first field that differs, so a difference reads as a cause, not a count.

Read only. Run: python -I -X utf8 tests/one-offs/thinking/k7_vs_v17_campaign_rows.py <original 1.8.1> <K7 chain> <v17>
"""
import collections
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator.savefile import read_save  # noqa: E402

DATABASES = ["living", "dead_unprunable", "landed_titles/landed_titles", "provinces", "county_manager/counties",
             "dynasties/dynasties", "dynasties/dynasty_house", "culture_manager/cultures", "religion/religions",
             "faiths/database", "artifacts/artifacts", "vassal_contracts/active", "armies/regiments"]
FIELD = re.compile(rb"\n\s*([A-Za-z_][\w.]*)=")


def entries(g, path):
    try:
        b = gs.locate(g, path)
    except gs.GamestateError:
        return {}
    return {e.key: g[e.open:e.close + 1] for e in gs.iter_entries(g, *b.body) if e.key}


def first_diff_field(a: bytes, b: bytes) -> str:
    la, lb = a.split(b"\n"), b.split(b"\n")
    for x, y in zip(la, lb):
        if x != y:
            m = FIELD.search(b"\n" + (x or y))
            return m.group(1).decode() if m else "(a line without a field)"
    return "(length: one has extra lines at the end)"


def main(orig, chain, v17):
    o, k, v = (read_save(p).gamestate for p in (orig, chain, v17))
    for path in DATABASES:
        eo, ek, ev = entries(o, path), entries(k, path), entries(v, path)
        camp = [i for i in eo if i in ek and i in ev]
        same = sum(ek[i] == ev[i] for i in camp)
        why = collections.Counter(first_diff_field(ev[i], ek[i]) for i in camp if ek[i] != ev[i])
        only = sum(1 for i in eo if (i in ek) != (i in ev))
        print(f"{path}: campaign rows {len(camp)} | identical {same} | differ {len(camp) - same}"
              f" | in one output only {only}" + (f" | first differing field: {why.most_common(6)}" if why else ""))


if __name__ == "__main__":
    main(*sys.argv[1:4])
