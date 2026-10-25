"""Print the first N bytes of a top-level section of a decompressed CK3 gamestate.

Usage: python -I section_head.py <gamestate> <key>[,<key>...] [nbytes]
Read-only. Scans for `^key=` at column 0 without loading the file into a parser.
"""
import re
import sys
from pathlib import Path


def main(gamestate: str, keys: str, nbytes: int) -> None:
    data = Path(gamestate).read_bytes()
    for key in keys.split(","):
        m = re.search(rb"^" + key.encode() + rb"\s*=", data, re.M)
        if not m:
            print(f"===== {key}: NOT FOUND")
            continue
        start = m.start()
        nxt = re.compile(rb"^[A-Za-z_][\w.]*\s*=", re.M).search(data, m.end())
        end = nxt.start() if nxt else len(data)
        chunk = data[start:min(end, start + nbytes)]
        print(f"===== {key}: offset {start:,}, section size {end - start:,} bytes")
        print(chunk.decode("utf-8", errors="replace"))
        if end - start > nbytes:
            print(f"... [{end - start - nbytes:,} more bytes]")
        print()


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 2000)
