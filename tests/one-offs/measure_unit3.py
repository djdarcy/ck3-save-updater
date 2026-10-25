"""Measurements behind the unit-3 subtractive rules (R1-R6), on the real extracted gamestates.

Usage: python -I tests/one-offs/measure_unit3.py
Read-only. Prints one block per rule question.
"""
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from ck3_save_migrator import gamestate as gs  # noqa: E402

OLD = ROOT / "private/data/extracted/987_10_27_husband_died/gamestate"
REF = ROOT / "private/data/extracted/ref_1_20_persia_867/gamestate"
BASELINE_ERR = ROOT / "private/data/runs/2026-10-24__20-19-01__baseline-orig-1.8.1-loadsave/logs/error.log"


def parent_path(data: bytes, pos: int, floor: int = 0) -> list[bytes]:
    """Keys of the enclosing blocks of pos (innermost last), by a backwards brace walk."""
    path = []
    depth = 0
    i = pos - 1
    while i >= floor:
        c = data[i]
        if c == 0x7D:
            depth += 1
        elif c == 0x7B:
            if depth == 0:
                k, _ = gs._key_before(data, i, floor)
                path.append(k or b"{}")
                if len(path) >= 4:
                    break
            else:
                depth -= 1
        i -= 1
    return list(reversed(path))


def main() -> None:
    old = OLD.read_bytes()
    ref = REF.read_bytes()

    print("== R1 converging")
    for name, d in (("1.8.1", old), ("1.20", ref)):
        total = len(re.findall(rb"\bconverging=\{", d))
        op = gs.find_section(d, "opinions")
        inside = len(re.findall(rb"\bconverging=\{", d[op.open:op.end]))
        print(f"  {name}: converging blocks total {total:,}, inside opinions {inside:,}")
    sample = Counter()
    for m in list(re.finditer(rb"\bconverging=\{", old))[:2000]:
        sample[b"/".join(parent_path(old, m.start(), max(0, m.start() - 4000))[-2:])] += 1
    print("  parents (first 2000):", dict(sample.most_common(5)))

    print("== R2 scripted_relations flags")
    for name, d in (("1.8.1", old), ("1.20", ref)):
        sr = len(re.findall(rb"\bscripted_relations=\{", d))
        flags = re.findall(rb'\bflags="([A-Za-z0-9+/=]*)"', d)
        print(f"  {name}: scripted_relations blocks {sr:,}; flags= values {len(flags):,}; "
              f"lengths {dict(Counter(len(f) for f in flags))}; distinct {dict(Counter(flags).most_common(6))}")
        kinds = Counter(m.group(1) for m in re.finditer(rb"scripted_relations=\{\s*([a-z_]+)=\{", d))
        print(f"     first relation kind per block: {dict(kinds.most_common(8))}")
    m = re.search(rb"scripted_relations=\{", ref)
    if m:
        print("  1.20 sample:", ref[m.start() - 200:m.start() + 300])

    print("== R3 title layout in the reference")
    lt = gs.locate(ref, "landed_titles/landed_titles")
    shown = 0
    keyorders = Counter()
    for t in gs.iter_entries(ref, *lt.body):
        kids = [c.key for c in gs.iter_children(ref, *t.body)]
        keyorders[tuple(k.decode() if k else "?" for k in kids[:6])] += 1
        tnd = [c for c in gs.iter_children(ref, *t.body) if c.key == b"title_name_data"]
        if tnd and shown < 3 and any(c.key == b"adj" for c in gs.iter_children(ref, *tnd[0].block.body)):
            print(ref[t.start:t.end].decode(errors="replace")[:900])
            print("  ---")
            shown += 1
    print("  most common first-6 key orders:")
    for k, n in keyorders.most_common(5):
        print(f"   {n:>6}  {k}")
    sub = Counter()
    for t in gs.iter_entries(ref, *lt.body):
        for c in gs.iter_children(ref, *t.body):
            if c.key == b"title_name_data":
                sub[tuple(x.key.decode() for x in gs.iter_children(ref, *c.block.body))] += 1
    print("  title_name_data key sets:")
    for k, n in sub.most_common(8):
        print(f"   {n:>6}  {k}")

    print("== R3 title name keys in 1.8.1")
    lt = gs.locate(old, "landed_titles/landed_titles")
    c = Counter()
    n = 0
    for t in gs.iter_entries(old, *lt.body):
        n += 1
        for ch in gs.iter_children(old, *t.body):
            if ch.key in (b"name", b"adj", b"pre", b"article", b"renamed", b"localization_key"):
                c[ch.key.decode()] += 1
    print(f"  titles {n:,}; key counts {dict(c)}")

    print("== R4 game_rules")
    for name, d in (("1.8.1", old), ("1.20", ref)):
        for m in re.finditer(rb"game_rules=\{", d):
            blk = gs.Block(b"game_rules", m.start(), m.end() - 1, gs.match_brace(d, m.end() - 1))
            body = d[blk.open:blk.end]
            where = "meta_data" if m.start() < gs.find_section(d, "meta_data").end else "top-level"
            keys = [ch.key for ch in gs.iter_children(d, *blk.body)]
            print(f"  {name} {where} at {m.start():,}: children {keys}; blanks {body.count(b'\"\"')}")

    print("== R5 empty-key entries")
    for name, d in (("1.8.1", old), ("1.20", ref)):
        hits = list(re.finditer(rb"(?m)^[ \t]*=", d))
        parents = Counter(b"/".join(parent_path(d, h.start(), max(0, h.start() - 3000))[-1:]) for h in hits)
        print(f"  {name}: {len(hits)} lines starting with '='; parents {dict(parents)}")

    print("== R6 dead title keys from the baseline error.log")
    err = BASELINE_ERR.read_text(encoding="utf-8", errors="replace")
    dead = re.findall(r"landed_title\.cpp:1169\]: (\S+) is not a valid title template", err)
    print(f"  {len(dead)} keys ({len(set(dead))} unique); first 5 {dead[:5]}")


if __name__ == "__main__":
    main()
