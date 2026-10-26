"""Which top-level sections does more than one rule parse? (director, 2026-10-25, after U16; no priority)

U16 found about 180 s of the 259 s migrate is parsing inside the rules. The question: is that the same sections
parsed again and again by different rules (a shared parsed view would cut it), or each rule parsing its own?

Runs ONE shape (faith) of the pipeline in-process, rules only (no lint, no write). Wraps the gamestate walkers the
rules call through `gs.` (iter_entries, iter_children, find_keys, child_at, locate, find_child, removal_span,
match_brace) and attributes the time of each OUTERMOST call to the top-level section its start offset falls in.
A call on another gamestate (the reference save, the old game's data) is labelled `other:<section>`.
Rule time not inside any walker (whole-save regexes, Python work on parsed values) is reported as `unattributed`.

Usage: python -I tests/one-offs/measure_shared_sections.py <save.ck3> <reference.ck3> <game dir> <old game dir>
"""
import bisect
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator import rules as R  # noqa: E402
from ck3_save_migrator import savefile as sf  # noqa: E402

acc = defaultdict(float)      # (rule, section) -> seconds in outermost walker calls
calls = defaultdict(int)      # (rule, section) -> outermost calls
current = ["setup"]
depth = [0]
save_ref = [None]
_maps: dict[int, tuple[bytes, list[int], list[tuple[int, str]]]] = {}


def section_of(data, pos) -> str:
    key = id(data)
    m = _maps.get(key)
    if m is None or m[0] is not data:
        depth[0] += 1                                  # _top_index calls match_brace: not a rule's walk
        try:
            top = gs._top_index(data) or {}
        finally:
            depth[0] -= 1
        spans = sorted((b.start, b.end, name.decode(errors="replace")) for name, bl in top.items() for b in bl)
        m = (data, [s for s, _, _ in spans], [(e, n) for _, e, n in spans])
        if len(_maps) > 8:
            _maps.clear()
        _maps[key] = m
    _, starts, rest = m
    i = bisect.bisect_right(starts, pos) - 1
    name = rest[i][1] if i >= 0 and pos < rest[i][0] else "(between sections)"
    mine = save_ref[0] is not None and data is save_ref[0].gamestate
    return name if mine else f"other:{name}"


def _where(a, k):
    data = a[0] if a else k.get("data")
    pos = None
    for x in a[1:]:
        if isinstance(x, int):
            pos = x
            break
        if hasattr(x, "start"):                        # a Block
            pos = x.start
            break
        if isinstance(x, list) and x and isinstance(x[0], int):
            pos = x[0]
            break
    return data, (pos if pos is not None else 0)


def wrap_fn(name):
    fn = getattr(gs, name)

    def inner(*a, **k):
        if depth[0]:
            return fn(*a, **k)
        data, pos = _where(a, k)
        sec = section_of(data, pos) if isinstance(data, (bytes, bytearray)) else "(no data)"
        depth[0] += 1
        t = time.perf_counter()
        try:
            return fn(*a, **k)
        finally:
            depth[0] -= 1
            acc[(current[0], sec)] += time.perf_counter() - t
            calls[(current[0], sec)] += 1
    setattr(gs, name, inner)


def wrap_gen(name):
    fn = getattr(gs, name)

    def inner(*a, **k):
        if depth[0]:
            yield from fn(*a, **k)
            return
        data, pos = _where(a, k)
        sec = section_of(data, pos) if isinstance(data, (bytes, bytearray)) else "(no data)"
        calls[(current[0], sec)] += 1
        it = fn(*a, **k)
        while True:
            depth[0] += 1
            t = time.perf_counter()
            try:
                item = next(it)
            except StopIteration:
                return
            finally:
                depth[0] -= 1
                acc[(current[0], sec)] += time.perf_counter() - t
            yield item                                     # the caller's work on the item is not counted here
    setattr(gs, name, inner)


def main():
    save_p, ref_p, game, old_game = sys.argv[1:5]
    for n in ("find_keys", "child_at", "locate", "find_child", "removal_span", "match_brace", "find_section"):
        wrap_fn(n)
    for n in ("iter_entries", "iter_children", "find_sections"):
        wrap_gen(n)

    save = sf.read_save(save_p)
    save_ref[0] = save
    ctx = R.RuleContext(game_dir=Path(game), reference=Path(ref_p), wos_shape="faith", old_game_dir=Path(old_game))
    rules = R.select("R1,R2,R3,R4,R5,R6,R11,R8,R10,R9,R12,R15,R14,R16,R7")
    rule_time = {}
    for r in rules:
        current[0] = r.id
        _maps.clear()
        t = time.perf_counter()
        R.run_rules(save, [r], ctx)
        rule_time[r.id] = time.perf_counter() - t

    total = sum(rule_time.values())
    walked = sum(acc.values())
    print(f"rules total {total:.0f}s; inside walkers {walked:.0f}s; unattributed {total - walked:.0f}s\n")

    print("PER RULE: rule time, walker time, top sections by walker time")
    for r in rules:
        mine = sorted(((s, v) for (rr, s), v in acc.items() if rr == r.id), key=lambda x: -x[1])
        w = sum(v for _, v in mine)
        top = ", ".join(f"{s} {v:.1f}" for s, v in mine[:5] if v >= 0.1)
        print(f"  {r.id:4} {rule_time[r.id]:6.1f}s  walkers {w:6.1f}s  {top}")

    print("\nSECTIONS WALKED BY MORE THAN ONE RULE (sum of walker seconds; rules that walked it with >= 0.1 s)")
    by_sec = defaultdict(dict)
    for (rr, s), v in acc.items():
        by_sec[s][rr] = by_sec[s].get(rr, 0) + v
    rows = []
    for s, per in by_sec.items():
        heavy = {rr: v for rr, v in per.items() if v >= 0.1}
        if len(heavy) >= 2:
            rows.append((sum(per.values()), s, heavy))
    shared = 0.0
    for tot, s, heavy in sorted(rows, reverse=True):
        shared += tot
        rs = ", ".join(f"{rr} {v:.1f}" for rr, v in sorted(heavy.items(), key=lambda x: -x[1]))
        print(f"  {s:34} {tot:6.1f}s  x{len(heavy):<2}  {rs}")
    print(f"\n  walker time in shared sections: {shared:.0f}s of {walked:.0f}s walker time, {total:.0f}s rule time")
    single = sum(tot for s, per in by_sec.items() for tot in [sum(per.values())]
                 if len([v for v in per.values() if v >= 0.1]) < 2)
    print(f"  walker time in sections only one rule walks: {single:.0f}s")


if __name__ == "__main__":
    main()
