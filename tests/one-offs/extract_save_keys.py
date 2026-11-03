"""extract_save_keys: every distinct key a real save of the game writes, for the S2 guard test (2026-11-03).

The guard (tests/test_shipped_keys.py) checks that no shipped patch writes a key the game does not define. It runs in
CI, without the game, against the key set this script takes once from a save the game itself wrote. The source used:
the 987 reference, a fresh 1.20.1.2 game started from the zz_ref bookmark mod and saved at once (vanilla content; the
mod adds only a bookmark). Keys are names before `=` (letters, digits, `_`, `.`, `:`), not numeric ids.

Usage: python -I tests/one-offs/extract_save_keys.py <save.ck3> <out.txt>
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ck3_save_migrator import savefile as sf  # noqa: E402

KEY = re.compile(rb"(?:^|[\s{])([A-Za-z_][A-Za-z0-9_.:]*)[ \t]*=", re.M)


def main():
    s = sf.read_save(sys.argv[1])
    keys = sorted({m.group(1).decode() for blob in (s.meta, s.gamestate) for m in KEY.finditer(blob)})
    ver = re.search(rb'(?m)^\tversion="([^"]*)"', s.meta)
    head = (f"# Every distinct key in {Path(sys.argv[1]).name} (game {ver.group(1).decode() if ver else '?'}),\n"
            f"# a save the game wrote itself; made by tests/one-offs/extract_save_keys.py. {len(keys)} keys.\n")
    Path(sys.argv[2]).write_text(head + "\n".join(keys) + "\n", encoding="utf-8")
    print(f"{len(keys)} keys -> {sys.argv[2]}")


if __name__ == "__main__":
    main()
