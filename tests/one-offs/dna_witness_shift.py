"""Is the 967 -> 987 DNA change a reordering (same genes, other positions) or a regeneration (new face)?

For sampled characters with DNA in both saves (524 B -> 532 B), measure against a CONTROL of unrelated pairs
(the 967 DNA of one character against the 987 DNA of another, chosen at random):
  aligned   share of byte positions equal at the same offset
  shifted   best share over byte shifts -16..+16 (a block of genes inserted or removed upstream)
  genes     share of the shorter's 4-byte groups found anywhere in the longer, as a multiset (a reordering)

If the same character's numbers sit well above the control, the face was carried and moved; if they sit at the
control, it was regenerated.

Usage: python -I tests/one-offs/dna_witness_shift.py <early.ck3> <late.ck3> [n]
"""
import base64
import random
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "one-offs"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ck3_save_migrator import savefile as sf  # noqa: E402
import dna_witness as W  # noqa: E402

dec = lambda s: base64.b64decode(s + b"=" * (-len(s) % 4))


def metrics(x: bytes, y: bytes):
    n = min(len(x), len(y))
    aligned = sum(x[k] == y[k] for k in range(n)) / n
    best = 0.0
    for d in range(-16, 17):
        m = sum(1 for k in range(len(x)) if 0 <= k + d < len(y) and x[k] == y[k + d])
        best = max(best, m / len(x))
    gx = Counter(x[k:k + 4] for k in range(0, len(x) - 3, 4))
    gy = Counter(y[k:k + 4] for k in range(0, len(y) - 3, 4))
    genes = sum((gx & gy).values()) / max(1, sum(gx.values()))
    return aligned, best, genes


def main():
    early, late = sys.argv[1], sys.argv[2]
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 300
    a = W.people(sf.read_save(early).gamestate)
    b = W.people(sf.read_save(late).gamestate)
    both = [i for i in a if i in b and a[i]["dna"] and b[i]["dna"]
            and (a[i]["name"], a[i]["birth"]) == (b[i]["name"], b[i]["birth"])]
    random.seed(11)
    sample = random.sample(both, min(n, len(both)))
    same = [metrics(dec(a[i]["dna"]), dec(b[i]["dna"])) for i in sample]
    ctrl = [metrics(dec(a[i]["dna"]), dec(b[random.choice(both)]["dna"])) for i in sample]
    avg = lambda rows, k: sum(r[k] for r in rows) / len(rows)
    print(f"{len(sample)} characters with DNA in both saves (of {len(both):,}); control = unrelated pairs")
    print(f"  {'':10} {'aligned':>8} {'shifted':>8} {'genes':>8}")
    print(f"  {'same':10} {avg(same, 0):8.3f} {avg(same, 1):8.3f} {avg(same, 2):8.3f}")
    print(f"  {'control':10} {avg(ctrl, 0):8.3f} {avg(ctrl, 1):8.3f} {avg(ctrl, 2):8.3f}")
    hi = sum(1 for s, c in zip(same, ctrl) if s[2] > c[2] + 0.2)
    print(f"  characters whose gene overlap beats their control by > 0.2: {hi} of {len(sample)}")

    # per 4-byte slot, aligned from the start: share of characters whose byte k of the slot is equal (same vs control)
    print("\nper gene slot (aligned from the start), share equal: byte0 byte1 byte2 byte3 | control byte0..3")
    pairs = [(dec(a[i]["dna"]), dec(b[i]["dna"])) for i in sample]
    cpairs = [(dec(a[i]["dna"]), dec(b[random.choice(both)]["dna"])) for i in sample]
    for slot in range(0, 131):
        row = []
        for ps in (pairs, cpairs):
            row.append([sum(x[slot * 4 + k] == y[slot * 4 + k] for x, y in ps) / len(ps) for k in range(4)])
        s, c = row
        flag = " <<" if min(s) > 0.9 else (" <" if sum(s) - sum(c) > 1.2 else "")
        print(f"  {slot:3}  {' '.join(f'{v:.2f}' for v in s)} | {' '.join(f'{v:.2f}' for v in c)}{flag}")

    print("\nlast 30 slots aligned from the END (slot -1 = last 4 bytes), share equal byte0..3 | control")
    for back in range(1, 31):
        row = []
        for ps in (pairs, cpairs):
            row.append([sum(x[len(x) - back * 4 + k] == y[len(y) - back * 4 + k] for x, y in ps) / len(ps)
                        for k in range(4)])
        s, c = row
        print(f"  {-back:4}  {' '.join(f'{v:.2f}' for v in s)} | {' '.join(f'{v:.2f}' for v in c)}")

    deltas = Counter()
    for x, y in pairs:
        for slot in range(3, 100):
            for k in (1, 3):
                if x[slot * 4 + k - 1] == y[slot * 4 + k - 1]:      # same template: compare the value
                    deltas[min(abs(x[slot * 4 + k] - y[slot * 4 + k]), 40) // 5 * 5] += 1
    tot = sum(deltas.values())
    print("\nmorph slots 3-99, same template: |value change| histogram (bins of 5, 40 = 40 or more)")
    print("  " + "  ".join(f"{d}: {v / tot:.2f}" for d, v in sorted(deltas.items())))


if __name__ == "__main__":
    main()
