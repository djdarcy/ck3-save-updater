"""Measure what a lint pass costs on a real migrated save, before deciding lint runs by default in migrate.

1. brace balance outside strings over the whole gamestate (one regex pass)
2. key-path collection: every key=, with its path of parent keys (numeric ids folded to '#')
   -- the input to "keys the 1.20 reference never has at this path"

Usage: python -I tests/one-offs/measure_lint_cost.py <save.ck3> [<reference.ck3>]
"""
import re
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ck3_save_migrator import savefile as sf  # noqa: E402

# a quoted string, a brace, or a key followed by '='
TOK = re.compile(rb'"(?:[^"\\]|\\.)*"|([{}])|([A-Za-z_][\w.:]*|\d[\d.]*)[ \t]*=')


def braces(g: bytes):
    depth, lo = 0, 0
    for m in re.finditer(rb'[{}]|"(?:[^"\\]|\\.)*"', g):
        c = g[m.start()]
        if c == 0x7B:
            depth += 1
        elif c == 0x7D:
            depth -= 1
            lo = min(lo, depth)
    return depth, lo


def key_paths(g: bytes, max_depth: int = 4) -> Counter:
    """(path tuple) -> count, path = parent keys then the key; numbers -> '#'; deeper than max_depth ignored."""
    out = Counter()
    stack: list[bytes] = []
    pending = None          # the key just seen with '=', which becomes the parent if a '{' follows
    for m in TOK.finditer(g):
        br, key = m.group(1), m.group(2)
        if br == b"{":
            stack.append(pending if pending is not None else b"{}")
            pending = None
        elif br == b"}":
            if stack:
                stack.pop()
            pending = None
        elif key is not None:
            k = b"#" if key[:1].isdigit() else key
            if len(stack) < max_depth:
                out[tuple(stack) + (k,)] += 1
            pending = k
        else:
            pending = None  # a quoted string
    return out


def main():
    paths = sys.argv[1:]
    for p in paths:
        t = time.perf_counter()
        g = sf.read_save(p).gamestate
        t_read = time.perf_counter() - t
        t = time.perf_counter()
        d, lo = braces(g)
        t_br = time.perf_counter() - t
        t = time.perf_counter()
        kp = key_paths(g)
        t_kp = time.perf_counter() - t
        print(f"{Path(p).name}: {len(g):,} bytes  read {t_read:.1f}s  braces {t_br:.1f}s (end depth {d}, min {lo})  "
              f"key paths {t_kp:.1f}s ({len(kp):,} distinct)")
    if len(paths) == 2:
        a = key_paths(sf.read_save(paths[0]).gamestate)
        b = set(key_paths(sf.read_save(paths[1]).gamestate))
        extra = [(k, n) for k, n in a.items() if k not in b]
        extra.sort(key=lambda kn: -kn[1])
        print(f"paths in {Path(paths[0]).name} never seen in the reference: {len(extra):,}")
        for k, n in extra[:20]:
            print(f"  {n:>9,}  {'/'.join(x.decode(errors='replace') for x in k)}")
        # key NAMES: absent from the reference anywhere, then absent from the engine binary's strings too
        names_ref = {k[-1] for k in b}
        unseen = Counter()
        for k, n in a.items():
            if k[-1] not in names_ref and k[-1] not in (b"#", b"{}"):
                unseen[k[-1]] += n
        t = time.perf_counter()
        exe = Path(r"E:\SteamLibrary\steamapps\common\Crusader Kings III\binaries\ck3.exe").read_bytes()
        exe_strings = set(re.findall(rb"[A-Za-z_][A-Za-z0-9_]{1,63}", exe))
        print(f"key names not in the reference: {len(unseen):,}; exe strings {len(exe_strings):,} "
              f"({len(exe)/1e6:.0f} MB, {time.perf_counter() - t:.1f}s)")
        missing = [(k, n) for k, n in unseen.most_common() if k not in exe_strings]
        print(f"  ... of which not in ck3.exe either: {len(missing)}")
        # script-defined names (event targets, flags) live in the game's own text files
        t = time.perf_counter()
        script = set()
        game = Path(r"E:\SteamLibrary\steamapps\common\Crusader Kings III\game")
        for sub in ("common", "events", "history", "gui", "map_data"):
            for f in (game / sub).rglob("*.txt"):
                script.update(re.findall(rb"[A-Za-z_][A-Za-z0-9_]{1,63}", f.read_bytes()))
        print(f"  script words {len(script):,} ({time.perf_counter() - t:.1f}s)")
        missing = [(k, n) for k, n in missing if k not in script]
        print(f"  ... of which not in the game's text files either: {len(missing)}")
        for k, n in missing[:60]:
            where = [p for p in a if p[-1] == k][:2]
            print(f"  {n:>9,}  {k.decode(errors='replace'):32} e.g. {' | '.join('/'.join(x.decode(errors='replace') for x in p) for p in where)}")


if __name__ == "__main__":
    main()
