"""S10 probe (2026-11-17 ~20:35): does the chain's 1.20-stamped output load once its dangling 1.21 references go?

S1's output (the founding 1.8.1 save through to_1_20 with the 1.21 reference, stamped 1.20.1.2) crashed 1.21.0 on
load (EXCEPTION_ACCESS_VIOLATION, run 2026-11-17__20-33-13__s10-chain-s1-resave). S1 had measured 4,195 province ->
district and 11,490 title -> trade_market references pointing at databases the save does not have: R14/R16 copied
1.21-shaped rows from the 1.21 reference. Hypothesis: strip those fields (the conversion of a 1.20 save builds districts
and markets itself) and the save loads.

Strips, in provinces' holdings: every `<x>_district=<id>`, `<x>_district_type=<x>`, `districts={...}`,
`regular_district_slot_limit=`; in provinces: `province_size_value=`, `province_size_level=`; in titles:
`trade_market=<id>`. Writes a NEW file only.
Run: python -I -X utf8 tests/one-offs/thinking/s10_strip_121_refs.py <in.ck3> <out.ck3>
"""
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator.savefile import read_save, write_save  # noqa: E402

PROV = re.compile(rb"\n\t+(?:\w*_district(?:_type)?=\S+|districts=\{[^{}]*\}|regular_district_slot_limit=\d+|"
                  rb"province_size_value=\S+|province_size_level=\d+)")
TITLE = re.compile(rb"\n\t+trade_market=\d+")


def strip(g: bytes) -> tuple[bytes, int, int]:
    pv, lt = gs.locate(g, "provinces"), gs.locate(g, "landed_titles/landed_titles")
    spans = sorted([(pv.open, pv.close, PROV), (lt.open, lt.close, TITLE)])
    out, pos, counts = [], 0, []
    for a, b, rx in spans:
        part, n = rx.subn(b"", g[a:b])
        out += [g[pos:a], part]
        pos = b
        counts.append(n)
    out.append(g[pos:])
    return b"".join(out), counts[0], counts[1]


def main(src, dst):
    s = read_save(src)
    g, np_, nt = strip(s.gamestate)
    s.set_gamestate(g)
    write_save(s, pathlib.Path(dst))
    print(f"stripped {np_} province fields and {nt} title trade_market lines -> {pathlib.Path(dst).name}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
