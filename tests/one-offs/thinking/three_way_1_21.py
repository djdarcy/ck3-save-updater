"""Patch day 1.21 (Silk & Silver), measure 1: the three-way comparison.

Saves: A = v17 (1.20.1.2, written by the tool), B = v17 re-saved by 1.21 (the game's own conversion),
C = the 1.21 reference (a fresh 1.21 game at 987.10.27). For every kind of entry any of them holds (20+ entries):
the entry counts in A/B/C, and the fields C's entries carry (filled on 90%+) that B lacks or leaves empty -- what the
conversion misses. Then, for the kinds 1.21 added, the first entry of each in B and C, raw, to see their shape.

Known-answer check: C against itself has no gaps, and C's kinds and fields equal the baseline built from it
(37 databases, 389 fields, scripts/make_field_baseline.py).
Run: python -I -X utf8 tests/one-offs/thinking/three_way_1_21.py <A> <B> <C>
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
from ck3_save_migrator._vendor.savediff import keys as K, text as T  # noqa: E402
from ck3_save_migrator.savefile import read_save  # noqa: E402

NEW = ("buildings/database", "districts/database", "roads/database", "trade_markets/database", "trade_routes/database")


def load(p):
    g = read_save(p).gamestate
    return g, T.SectionIndex(g)


def main(a, b, c):
    (ga, ia), (gb, ib), (gc, ic) = load(a), load(b), load(c)
    paths = sorted(set(K.database_paths(ga, ia)) | set(K.database_paths(gb, ib)) | set(K.database_paths(gc, ic)))
    cc = {p: K.field_coverage(gc, ic, p) for p in paths}
    # known answer: C has no gaps against itself
    self_gaps = sum(len(K.coverage_gaps(cc[p], cc[p])) for p in paths if cc[p]["entries"])
    print(f"known answer: C against itself, {self_gaps} gap rows (expect 0); kinds with C entries: "
          f"{sum(1 for p in paths if cc[p]['entries'] >= 20)}; fields: {sum(len(cc[p]['fields']) for p in paths if cc[p]['entries'] >= 20)}")
    print(f"\n{'kind':52} {'A v17':>8} {'B resave':>9} {'C ref':>8}  B lacks (C carries it on 90%+)")
    for p in paths:
        ca, cb = K.field_coverage(ga, ia, p), K.field_coverage(gb, ib, p)
        gaps = K.coverage_gaps(cb, cc[p]) if cb["entries"] and cc[p]["entries"] else []
        note = ", ".join(f"{r['field']} {r['missing'] + r['empty']}/{r['entries']}" for r in gaps[:6])
        if not cb["entries"] and cc[p]["entries"]:
            note = "ABSENT in the re-save"
        print(f"{p:52} {ca['entries']:>8} {cb['entries']:>9} {cc[p]['entries']:>8}  {note}")
    for p in NEW:
        for name, g, i in (("B resave", gb, ib), ("C ref", gc, ic)):
            blk = T.locate(i, p)
            if blk is None:
                print(f"\n{p} [{name}]: absent")
                continue
            e = next(T.iter_entries(g, *blk.body), None)
            print(f"\n{p} [{name}] first entry {e.key if e else None!r}:\n{g[e.open:e.open + 600].decode('utf-8', 'replace') if e else ''}")


if __name__ == "__main__":
    main(*sys.argv[1:4])
