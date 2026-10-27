"""archive_files: move listed files to an archive root on another drive, keeping their path relative to a base.

Each file is copied (metadata kept), the copy's size checked against the original, and only then the original
removed. A file whose copy does not match stays where it is. Prints a summary and writes a manifest beside the
archive (original path, archive path, bytes).

2026-10-27, djdarcy: the converted screenshot PNGs go to E: ("We can just move the files to e:\") to free C:.

Usage: python -I tests/one-offs/archive_files.py <list of files> <base folder> <archive root>
"""
from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path


def main():
    listing, base, root = Path(sys.argv[1]), Path(sys.argv[2]).resolve(), Path(sys.argv[3])
    files = [Path(x) for x in listing.read_text(encoding="utf-8").split("\n") if x.strip()]
    moved = kept = 0
    total = 0
    lines = []
    for f in files:
        f = f.resolve()
        if not f.exists():
            continue
        dest = root / f.relative_to(base)
        dest.parent.mkdir(parents=True, exist_ok=True)
        size = f.stat().st_size
        shutil.copy2(f, dest)
        if dest.stat().st_size == size:
            f.unlink()
            moved += 1
            total += size
            lines.append(f"{f}\t{dest}\t{size}")
        else:
            kept += 1
            print(f"size mismatch, original kept: {f}")
    manifest = root / f"_manifest_{time.strftime('%Y-%m-%d__%H-%M-%S')}.tsv"
    manifest.write_text("original\tarchive\tbytes\n" + "\n".join(lines) + "\n", encoding="utf-8")
    print(f"moved {moved} files ({total / 1e9:.2f} GB) to {root}; kept {kept}; manifest {manifest}")


if __name__ == "__main__":
    main()
