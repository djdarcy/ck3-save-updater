"""Inspect a CK3 .ck3 save: header, metadata, zip members, top-level gamestate keys.

Usage: python -I inspect_save.py <save.ck3> <out_dir>
Writes the decompressed gamestate + meta to out_dir; never modifies the input.
"""
import hashlib
import io
import re
import sys
import zipfile
from pathlib import Path


def main(save_path: str, out_dir: str) -> None:
    src = Path(save_path)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    raw = src.read_bytes()
    print(f"file      : {src.name}")
    print(f"size      : {len(raw):,} bytes  sha256={hashlib.sha256(raw).hexdigest()[:16]}")

    header = raw[:raw.index(b"\n")].decode("ascii")
    # SAV + 2 hex version + 2 hex type + 8 hex random + 8 hex meta length (observed layout)
    print(f"header    : {header}")
    print(f"  type    : {header[5:7]} (00 text, 01 binary, 02 zipped text, 03 zipped binary)")

    zip_at = raw.find(b"PK\x03\x04")
    print(f"zip offset: {zip_at:,}")
    (out / "header_meta.txt").write_bytes(raw[:zip_at])

    with zipfile.ZipFile(io.BytesIO(raw[zip_at:])) as zf:
        for info in zf.infolist():
            print(f"  member  : {info.filename:12} {info.compress_size:>12,} -> {info.file_size:>14,}")
            zf.extract(info, out)

    gs = (out / "gamestate").read_bytes()
    print(f"gamestate first bytes: {gs[:40]!r}")
    text = gs.decode("utf-8", errors="replace")

    # top-level keys: lines with no leading whitespace of the form key=
    sizes = {}
    order = []
    positions = [(m.start(), m.group(1)) for m in re.finditer(r"^([A-Za-z_][\w.]*)\s*=", text, re.M)]
    for i, (pos, key) in enumerate(positions):
        end = positions[i + 1][0] if i + 1 < len(positions) else len(text)
        if key not in sizes:
            order.append(key)
        sizes[key] = sizes.get(key, 0) + (end - pos)
    print(f"top-level keys: {len(order)}")
    for k in sorted(order, key=lambda k: -sizes[k]):
        print(f"  {sizes[k]:>14,}  {k}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
