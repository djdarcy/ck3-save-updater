"""mod_error_attribution: which of the loaded mods' own files the game's error.log names, and how often.

2026-10-27: settling the first-play playset ("current, on disk and working", djdarcy). One game run with every
candidate enabled; this reads that run's error.log and, per mod, counts the lines that name a file the mod itself
ships (common/, events/, gfx/, gui/, localization/ paths). A file several mods ship is counted for each, and
listed as shared. A mod with 0 lines is not proven to work (a mod can fail silently); it logged nothing.

Usage: python -I tests/one-offs/mod_error_attribution.py <error.log> <mod folder>... [--top N]
"""
from __future__ import annotations

import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

PATH = re.compile(r'(?:file: "?|in file: ")((?:common|events|gfx|gui|localization|history|map_data)/[^" \n]+?\.'
                  r'(?:txt|gui|yml|csv))')


def mod_name(folder: Path) -> str:
    d = folder / "descriptor.mod"
    if d.exists():
        m = re.search(r'^name="([^"]*)"', d.read_text(encoding="utf-8", errors="replace"), re.M)
        if m:
            return m.group(1)
    return folder.name


def main():
    args = sys.argv[1:]
    top = int(args[args.index("--top") + 1]) if "--top" in args else 3
    args = [a for i, a in enumerate(args) if a != "--top" and (i == 0 or args[i - 1] != "--top")]
    log, folders = Path(args[0]), [Path(a) for a in args[1:]]
    owners = defaultdict(set)
    for f in folders:
        for p in f.rglob("*"):
            if p.is_file():
                owners[p.relative_to(f).as_posix()].add(f)
    hits = Counter()
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        for m in PATH.finditer(line):
            hits[m.group(1)] += 1
    print(f"{log}: {sum(hits.values()):,} file mentions, {len(hits):,} distinct files")
    for f in folders:
        mine = {p: n for p, n in hits.items() if f in owners.get(p, ())}
        shared = [p for p in mine if len(owners[p]) > 1]
        total = sum(mine.values())
        flag = "  <-- logs errors" if total else ""
        print(f"{total:>7,}  {mod_name(f)[:44]:44} ({len(mine)} files{', ' + str(len(shared)) + ' shared' if shared else ''}){flag}")
        for p, n in sorted(mine.items(), key=lambda x: -x[1])[:top]:
            print(f"           {n:>6,}  {p}")


if __name__ == "__main__":
    main()
