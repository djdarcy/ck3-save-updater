"""Where in the save do the names behind the game's error.log families live? (measurement for lint's family checks)

For every "Failed to read key reference: X" name and "Unknown on action: X" in an error.log, find the save fields
that hold X as a value: `field=X`, `field="X"`, or X inside `field={ ... }`. Prints, per field, how many log lines
its names account for -- the contexts lint must check. Also: DNA string lengths (save vs reference), where
owner_influence/exposure_* sit, dynasty template keys, and whether culture names appear in the log.

Usage: python -I tests/one-offs/lint_family_contexts.py <error.log> <migrated .ck3> [<reference .ck3>]
"""
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from ck3_save_migrator import savefile as sf  # noqa: E402


def main():
    log = Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace").splitlines()
    g = sf.read_save(sys.argv[2]).gamestate
    ref = sf.read_save(sys.argv[3]).gamestate if len(sys.argv) > 3 else None

    kref = Counter(m.group(1) for l in log for m in [re.search(r"Failed to read key reference: ([^:]+):", l)] if m)
    onact = Counter(m.group(1) for l in log for m in [re.search(r"Unknown on action: (\S+)", l)] if m)
    print(f"key references: {sum(kref.values()):,} lines, {len(kref)} names; on actions: {sum(onact.values()):,} lines, {len(onact)} names")

    # one pass: every scalar value and every flat-list token, indexed by the field that holds it
    by_value: dict[str, Counter] = defaultdict(Counter)
    for m in re.finditer(rb'([A-Za-z_]\w*)[ \t]*=[ \t]*(?:"([^"\n]*)"|([A-Za-z_][\w.\-]*)|\{([^{}]*)\})', g):
        field = m.group(1).decode()
        if m.group(4) is not None:
            for tok in m.group(4).split():
                by_value[tok.strip(b'"').decode("utf-8", "replace")][field + "={}"] += 1
        else:
            by_value[(m.group(2) if m.group(2) is not None else m.group(3)).decode("utf-8", "replace")][field] += 1

    for label, names in (("KEY REFERENCES", kref), ("ON ACTIONS", onact)):
        ctx_lines, ctx_names, ctx_occ = Counter(), defaultdict(set), Counter()
        unplaced = []
        for name, n in names.items():
            fields = by_value.get(name, Counter())
            if not fields:
                unplaced.append((name, n))
                continue
            top = fields.most_common(1)[0][0]
            ctx_lines[top] += n
            ctx_names[top].add(name)
            ctx_occ[top] += sum(fields.values())
        print(f"\n== {label}: log lines by the save field holding the name (occurrences in save)")
        for f, n in ctx_lines.most_common(30):
            ex = sorted(ctx_names[f])[:3]
            print(f"  {n:>6,} lines  {len(ctx_names[f]):>4} names  {ctx_occ[f]:>7,} occ  {f:34} e.g. {ex}")
        if unplaced:
            print(f"  not found as a value in the save: {len(unplaced)} names, {sum(n for _, n in unplaced):,} lines; "
                  f"e.g. {unplaced[:8]}")

    dna = Counter(len(m.group(1)) for m in re.finditer(rb'\n\t+dna="([^"]*)"', g))
    print(f"\nDNA lengths in the save: {dna.most_common(6)}  (total {sum(dna.values()):,})")
    if ref is not None:
        rdna = Counter(len(m.group(1)) for m in re.finditer(rb'\n\t+dna="([^"]*)"', ref))
        print(f"DNA lengths in the reference: {rdna.most_common(6)}")
    for tok in (b"owner_influence", b"exposure_type", b"exposure_marker"):
        lines = [g[g.rfind(b"\n", 0, m.start()) + 1:m.end() + 20] for m in re.finditer(rb"\n\t*" + tok + rb"=", g)][:2]
        print(f"{tok.decode()}: {len(re.findall(rb'[\n\t]' + tok + rb'=', g)):,} in save; e.g. {lines}")
    culture_hits = [l for l in log if re.search(r"czech|slovien|scottish|carantanian", l, re.I)]
    print(f"culture-name lines in the log: {len(culture_hits)}; e.g. {[l[:160] for l in culture_hits[:3]]}")
    dyn = [l for l in log if "dynasty template" in l][:3]
    print(f"dynasty template lines e.g. {[l[:160] for l in dyn]}")
    dup = [i for i, l in enumerate(log) if "Duplicate landed title name" in l][:2]
    print(f"duplicate title name lines e.g. {[log[i][:120] + ' || ' + log[i + 1][:120] for i in dup]}")
    sse = [i for i, l in enumerate(log) if "Script system error!" in l][:2]
    print(f"script system error e.g. {[' || '.join(x[:120] for x in log[i:i + 4]) for i in sse]}")


if __name__ == "__main__":
    main()
