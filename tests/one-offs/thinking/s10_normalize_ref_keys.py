"""S10, the collab's round-1 finding (2026-11-18 16:05): does the chain stop duplicating the world once 1.21 title keys read?

1.21 writes a title's key on its type line (`type=title_type_x\tkey=c_y`), and the package's key patterns need a newline
before `key=` (translate.py:85 and eight more sites). With the 1.21 reference, 19 of its 20,499 titles had a readable key,
so the transplant joined none and copied the whole title database (12,086 keys held twice in the chain save).

This writes a scratch COPY of a reference save with each such `\tkey=` moved to its own line, so the existing code reads
it unchanged. The original is never written. A one-off for the measurement only; the real fix reads both layouts.
Run: python -I -X utf8 tests/one-offs/thinking/s10_normalize_ref_keys.py <reference.ck3> <out.ck3>
"""
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
from ck3_save_migrator.savefile import read_save, write_save  # noqa: E402

SAME_LINE = re.compile(rb"(\n(\t+)type=[^\s]*)\t(key=)")


def main(src, dst):
    dst = pathlib.Path(dst)
    assert not dst.exists(), f"{dst} exists; this writes new files only"
    s = read_save(src)
    g, n = SAME_LINE.subn(lambda m: m.group(1) + b"\n" + m.group(2) + m.group(3), s.gamestate)
    s.set_gamestate(g)
    write_save(s, dst)
    print(f"{dst.name}: {n} keys moved to their own line")


if __name__ == "__main__":
    main(*sys.argv[1:3])
