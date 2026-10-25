"""U12 planning: how big is each CK3 version's script layer (common, events, history, English localization,
the province definition files), from DepotDownloader's -manifest-only text of the main content depot (1158311)?

Applies the same regexes as the -filelist (DepotDownloader matches paths with forward slashes) to each manifest,
and prints per-version file counts and bytes, so the download size is known before anything moves.

Usage: python -I tests/one-offs/version_scripts_plan.py <filelist.txt> <manifest txt> [<manifest txt> ...]
"""
import re
import sys
from pathlib import Path

ROW = re.compile(r"^\s*(\d+)\s+(\d+)\s+([0-9a-f]{40})\s+([0-9a-fA-F]+)\s+(.+?)\s*$")


def main():
    pats = [re.compile(line[len("regex:"):]) for line in Path(sys.argv[1]).read_text().splitlines()
            if line.startswith("regex:")]
    total = 0
    print(f"{'manifest':45} {'files':>7} {'MB':>9}")
    for mf in sys.argv[2:]:
        n, size = 0, 0
        for line in Path(mf).read_text(encoding="utf-8", errors="replace").splitlines():
            m = ROW.match(line)
            if not m or int(m.group(4), 16) & 0x40:
                continue
            name = m.group(5).replace("\\", "/")
            if any(p.search(name) for p in pats):
                n += 1
                size += int(m.group(1))
        total += size
        print(f"{Path(mf).parent.name + '/' + Path(mf).name[:30]:45} {n:>7,} {size / 1e6:>9.1f}")
    print(f"{'total':45} {'':>7} {total / 1e6:>9.1f}")


if __name__ == "__main__":
    main()
