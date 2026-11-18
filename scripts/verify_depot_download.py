"""Verify a DepotDownloader download against its manifests: every file present, right size, right SHA-1.

Input:
  manifests dir  - holds DepotDownloader's -manifest-only text files (manifest_<depot>_<manifest>.txt)
  hashes.csv     - the downloaded tree, hashed where it lives: columns Path,Length,Hash (SHA-1, as written by
                   PowerShell Get-FileHash), Path relative to the download folder
  depot:manifest - the pairs that were downloaded (only those manifests count)

Usage: python -I tests/one-offs/verify_depot_download.py <manifests dir> <hashes.csv> 1158311:2013027804061508407 ...
"""
import csv
import re
import sys
from pathlib import Path

ROW = re.compile(r"^\s*(\d+)\s+(\d+)\s+([0-9a-f]{40})\s+([0-9a-fA-F]+)\s+(.+?)\s*$")
EMPTY_SHA1 = "da39a3ee5e6b4b0d3255bfef95601890afd80709"


def expected(mdir: Path, pairs: list[tuple[str, str]]) -> tuple[dict, list]:
    files, dupes = {}, []
    for depot, manifest in pairs:
        f = mdir / f"manifest_{depot}_{manifest}.txt"
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            m = ROW.match(line)
            if not m:
                continue
            size, _chunks, sha, flags, name = m.groups()
            if int(flags, 16) & 0x40:      # directory entry (the flags column is printed in hex: "40")
                continue
            if int(size) == 0 and sha == "0" * 40:
                sha = EMPTY_SHA1            # the manifest writes zeros for an empty file; its real SHA-1 is this
            key = name.replace("/", "\\").lower()
            if key in files:
                dupes.append((key, files[key][2], depot))
            files[key] = (int(size), sha, depot)
    return files, dupes


def main():
    mdir, csv_path = Path(sys.argv[1]), Path(sys.argv[2])
    pairs = [tuple(a.split(":")) for a in sys.argv[3:]]
    want, dupes = expected(mdir, pairs)
    have = {}
    with csv_path.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            have[row["Path"].replace("/", "\\").lower()] = (int(row["Length"]), row["Hash"].lower())
    tool = {k for k in have if k.startswith(".depotdownloader\\")}
    missing = sorted(k for k in want if k not in have)
    extra = sorted(k for k in have if k not in want and k not in tool)
    size_bad = sorted(k for k in want if k in have and have[k][0] != want[k][0])
    sha_bad = sorted(k for k in want if k in have and have[k][0] == want[k][0] and have[k][1] != want[k][1])
    print(f"expected files: {len(want):,} ({sum(v[0] for v in want.values()):,} bytes) from {len(pairs)} manifests")
    print(f"downloaded files: {len(have) - len(tool):,} (+{len(tool)} in .DepotDownloader)")
    print(f"missing {len(missing)}, extra {len(extra)}, size mismatch {len(size_bad)}, SHA-1 mismatch {len(sha_bad)}, "
          f"paths in two depots {len(dupes)}")
    for label, items in (("missing", missing), ("extra", extra), ("size", size_bad), ("sha1", sha_bad), ("dupes", dupes)):
        if items:
            print(f"  {label}: {items[:10]}")
    ok = not (missing or extra or size_bad or sha_bad)
    print("VERIFIED: every file present with the manifest's size and SHA-1" if ok else "NOT VERIFIED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
