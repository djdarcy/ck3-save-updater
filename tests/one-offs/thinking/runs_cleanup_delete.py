"""Delete exactly the files on the signed runs-cleanup list, with djdarcy's condition (2026-11-07): "as long as we're
sure the ones that are duplicates have ONE of those duplicates that isn't deleted (as a backup)".

For each row of the list (path, sha256, bytes, reason):
  1. the file exists and its sha256 still equals the listed one (else skipped, reported);
  2. a duplicate ("dup-of-kept ...") is deleted only when an identical file NOT on the list exists right now: found
     by size among the run saves and the Documents save games, then confirmed by sha256 (else skipped, reported).
A plain delete (os.remove), never anything not on the list. Prints a per-reason account and the bytes freed.
Run: python -I tests/one-offs/thinking/runs_cleanup_delete.py <list.tsv>
"""
import hashlib
import os
import sys
from collections import defaultdict
from pathlib import Path

RUNS = Path(r"C:\code\ck3-save-migrator\private\data\runs")
DOCS = Path.home() / "Documents" / "Paradox Interactive" / "Crusader Kings III" / "save games"


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(8 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


rows = [ln.split("\t") for ln in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()[1:] if ln.strip()]
listed = {Path(p) for p, *_ in rows}
by_size = defaultdict(list)                        # every save not on the list, by size: the possible kept copies
for f in list(RUNS.rglob("*.ck3")) + (list(DOCS.glob("*.ck3")) if DOCS.is_dir() else []):
    if f not in listed:
        by_size[f.stat().st_size].append(f)
kept_copy: dict[str, Path | None] = {}


def a_kept_copy(h: str, size: int) -> Path | None:
    if h not in kept_copy:
        kept_copy[h] = next((f for f in by_size.get(size, []) if f.exists() and sha(f) == h), None)
    return kept_copy[h]


done = defaultdict(lambda: [0, 0])
skipped = []
for p, h, size, why in rows:
    f, size = Path(p), int(size)
    if not f.is_file():
        skipped.append((p, "missing"))
        continue
    if sha(f) != h:
        skipped.append((p, "sha256 changed since the list"))
        continue
    if why.startswith("dup-of-kept"):
        keep = a_kept_copy(h, size)
        if keep is None:
            skipped.append((p, "no kept copy found: not deleted"))
            continue
    os.remove(f)
    done[why][0] += 1
    done[why][1] += size
for why, (n, s) in done.items():
    print(f"deleted  {why}: {n} files, {s / 1e9:.1f} GB")
print(f"deleted in all: {sum(n for n, _ in done.values())} files, {sum(s for _, s in done.values()) / 1e9:.1f} GB")
print(f"skipped: {len(skipped)}")
for p, r in skipped:
    print(f"  {r}: {p}")
