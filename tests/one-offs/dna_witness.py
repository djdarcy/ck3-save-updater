"""Second witness for DNA (djdarcy via the director, 2026-10-25): the 987 save went through his own rougher
migrations (1.5 -> 1.7.2 -> 1.8.1); an earlier save of the same campaign (967, 1.5.1.1) shows what was there before.

For each save: game version, portraits_version, DNA length histogram over living + dead_unprunable +
characters/dead_prunable. Then characters joined by FULL id (slot + generation byte): a slot reused at another
generation is a different person and never joins; those are counted and excluded. A joined pair whose first_name
or birth differ is counted as a suspect join.

DNA pairs are classed: identical / same length, different / different length / 967-only / 987-only (has DNA in
one save only, or the character exists in one save only). Ten "different" pairs are sampled with their traits and
skills (prowess is the sixth skill in these versions) beside the DNA.

Neither save is authoritative: the output states disagreements by kind and decides nothing.

Usage: python -I tests/one-offs/dna_witness.py <early.ck3> <late.ck3> [--samples 10]
"""
import base64
import random
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator import savefile as sf  # noqa: E402

SECTIONS = ("living", "dead_unprunable", "characters/dead_prunable")


def field(blob: bytes, name: bytes):
    """A field at the entry's own first level; the indent is read from the entry (1.5 saves nest one tab deeper)."""
    ind = re.match(rb"[^\n]*\n(\t*)", blob)
    tabs = ind.group(1) if ind else b"\t"
    m = re.search(rb"\n" + re.escape(tabs) + name + rb"=(\"[^\"]*\"|\{[^{}]*\}|[^\s{}]+)", blob)
    return m.group(1).strip(b'"') if m else None


def people(g: bytes) -> dict[int, dict]:
    out = {}
    for path in SECTIONS:
        try:
            b = gs.locate(g, path)
        except gs.GamestateError:
            continue
        for e in gs.iter_entries(g, *b.body):
            if not (e.key and e.key.isdigit()):
                continue
            blob = g[e.start:e.end]
            out[int(e.key)] = {
                "where": path,
                "name": field(blob, b"first_name"),
                "birth": field(blob, b"birth"),
                "dna": field(blob, b"dna"),
                "traits": field(blob, b"traits"),
                "skill": field(blob, b"skill"),
            }
    return out


def meta(g: bytes, key: bytes):
    m = re.search(rb"\n\t" + key + rb"=\"?([^\s\"]+)", g[:5000])
    return m.group(1).decode() if m else "?"


def main():
    early_p, late_p = sys.argv[1], sys.argv[2]
    n_samples = int(sys.argv[sys.argv.index("--samples") + 1]) if "--samples" in sys.argv else 10
    saves = []
    for p in (early_p, late_p):
        g = sf.read_save(p).gamestate
        ppl = people(g)
        saves.append(ppl)
        lens = Counter(len(v["dna"]) for v in ppl.values() if v["dna"])
        print(f"{Path(p).name}\n  version {meta(g, b'version')}, portraits_version {meta(g, b'portraits_version')}, "
              f"characters {len(ppl):,}, with dna {sum(lens.values()):,}")
        print("  dna lengths: " + ", ".join(f"{n}: {c:,}" for n, c in lens.most_common()))
    a, b = saves

    slot = lambda i: i & 0xFFFFFF
    a_slots = {slot(i): i for i in a}
    regen = sum(1 for i in b if i not in a and slot(i) in a_slots)
    joined = [i for i in a if i in b]
    suspect = [i for i in joined if (a[i]["name"], a[i]["birth"]) != (b[i]["name"], b[i]["birth"])]
    print(f"\njoin by full id: {len(joined):,} pairs; slot reused at another generation (excluded): {regen:,}; "
          f"suspect joins (first_name or birth differ): {len(suspect):,}")
    for i in suspect[:3]:
        print(f"  #{i}: {a[i]['name']} {a[i]['birth']}  vs  {b[i]['name']} {b[i]['birth']}")
    good = [i for i in joined if i not in set(suspect)]

    cls = Counter()
    different = []
    for i in good:
        da, db = a[i]["dna"], b[i]["dna"]
        if da and db:
            if da == db:
                cls["identical"] += 1
            elif len(da) == len(db):
                cls["same length, different"] += 1
                different.append(i)
            else:
                cls[f"different length ({len(da)} -> {len(db)})"] += 1
        elif da:
            cls["dna in 967 only"] += 1
        elif db:
            cls["dna in 987 only"] += 1
        else:
            cls["no dna in either"] += 1
    cls["character in 967 only"] = sum(1 for i in a if i not in b)
    cls["character in 987 only"] = sum(1 for i in b if i not in a)
    print("\nDNA pairs (joined, suspects excluded):")
    for k, v in cls.most_common():
        print(f"  {k:40} {v:>8,}")

    lost = Counter((a[i]["where"], b[i]["where"]) for i in good if a[i]["dna"] and not b[i]["dna"])
    print("\n'dna in 967 only', by section 967 -> 987:")
    for (wa, wb), v in lost.most_common():
        print(f"  {wa:26} -> {wb:26} {v:>8,}")
    gained = Counter((a[i]["where"], b[i]["where"]) for i in good if b[i]["dna"] and not a[i]["dna"])
    print("'dna in 987 only', by section 967 -> 987:")
    for (wa, wb), v in gained.most_common():
        print(f"  {wa:26} -> {wb:26} {v:>8,}")

    # different length: is the longer one the shorter with bytes inserted at one place?
    dec = lambda s: base64.b64decode(s + b"=" * (-len(s) % 4))
    shapes, other = Counter(), 0
    resized = [i for i in good if a[i]["dna"] and b[i]["dna"] and len(a[i]["dna"]) != len(b[i]["dna"])]
    for i in resized:
        x, y = dec(a[i]["dna"]), dec(b[i]["dna"])
        p = 0
        while p < min(len(x), len(y)) and x[p] == y[p]:
            p += 1
        s = 0
        while s < min(len(x), len(y)) - p and x[-1 - s] == y[-1 - s]:
            s += 1
        if p + s >= len(x):
            shapes[(len(x), len(y), f"pure insertion of {len(y) - len(x)} bytes at offset {p}")] += 1
        else:
            gap = len(x) - p - s
            shapes[(len(x), len(y), f"prefix {p} B same, suffix {s} B same, {gap} B of the shorter differ")] += 1
    print(f"\ndifferent-length pairs, decoded ({len(resized):,}):")
    for (lx, ly, what), v in shapes.most_common(12):
        print(f"  {lx} B -> {ly} B: {what:60} {v:>7,}")

    ts = Counter((a[i]["traits"] == b[i]["traits"], a[i]["skill"] == b[i]["skill"]) for i in good)
    print("\nall joined pairs: (traits same, skills same) -> count")
    for k, v in ts.most_common():
        print(f"  {k}: {v:,}")
    different = different or resized

    print(f"\n{n_samples} sampled 'different' pairs (same length if any exist, else different length):")
    random.seed(7)
    for i in random.sample(different, min(n_samples, len(different))):
        da, db = dec(a[i]["dna"]), dec(b[i]["dna"])
        diff = [k for k in range(min(len(da), len(db))) if da[k] != db[k]]
        print(f"  #{i} {a[i]['name'].decode(errors='replace')} b.{a[i]['birth'].decode()} ({a[i]['where']} -> {b[i]['where']})")
        print(f"     dna bytes differing: {len(diff)} of {len(da)}; first offsets {diff[:12]}")
        for f in ("traits", "skill"):
            same = a[i][f] == b[i][f]
            print(f"     {f:6} {'same' if same else 'DIFFERENT'}: {a[i][f]!r}" + ("" if same else f" -> {b[i][f]!r}"))


if __name__ == "__main__":
    main()
