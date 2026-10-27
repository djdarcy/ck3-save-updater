"""title_cycles: is there a cycle in any title's chain of parents? (2026-10-27: the game hangs on 987.11.8 in a
tight loop that walks landed titles through a parent field until it reaches a target title or tier; a chain that
returns to itself never ends.)

For each landed title, follows de_jure_liege and, separately, de_facto_liege upward; reports every cycle found
(by title keys), titles whose parent is themselves, parents that are not titles, and the longest chains.

Usage: python -I tests/one-offs/title_cycles.py <save.ck3> [<save.ck3> ...]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator import savefile as sf  # noqa: E402

KEY = re.compile(rb'\n\tkey="?([^"\s]+)"?')


def load(path: str) -> bytes:
    raw = Path(path).read_bytes()
    if raw[:3] == b"SAV" and raw[5:7] == b"00":
        return raw[raw.index(b"\n") + 1:]
    return sf.read_save(path).gamestate


def main():
    for path in sys.argv[1:]:
        g = load(path)
        b = gs.locate(g, "landed_titles/landed_titles")
        key, parent = {}, {"de_jure_liege": {}, "de_facto_liege": {}}
        for e in gs.iter_entries(g, *b.body):
            if not (e.key and e.key.isdigit()):
                continue
            body = g[e.start:e.end]
            i = int(e.key)
            m = KEY.search(body)
            key[i] = m.group(1).decode() if m else f"#{i}"
            for f in parent:
                pm = re.search(rb"\n\t" + f.encode() + rb"=(\d+)", body)
                if pm:
                    parent[f][i] = int(pm.group(1))
        print(f"== {Path(path).name}: {len(key)} titles")
        for f, par in parent.items():
            cycles, self_loops, dangling, longest = set(), [], [], (0, None)
            for start in par:
                seen, cur, n = [], start, 0
                while cur in par:
                    if cur in seen:
                        cyc = seen[seen.index(cur):]
                        cycles.add(tuple(sorted(cyc)))
                        break
                    seen.append(cur)
                    cur = par[cur]
                    n += 1
                if par.get(start) == start:
                    self_loops.append(start)
                if par[start] not in key:
                    dangling.append(start)
                if n > longest[0]:
                    longest = (n, start)
            print(f"  {f}: {len(par)} titles with one; cycles {len(cycles)}; self-parents {len(self_loops)}; "
                  f"parent not a title {len(dangling)}; longest chain {longest[0]} (from {key.get(longest[1])})")
            for cyc in sorted(cycles)[:20]:
                chain = [cyc[0]]
                while par[chain[-1]] != cyc[0]:
                    chain.append(par[chain[-1]])
                print("    cycle: " + " -> ".join(f"{key[c]}({c})" for c in chain) + f" -> {key[cyc[0]]}")
            for s in self_loops[:10]:
                print(f"    self-parent: {key[s]}({s})")
            for d in dangling[:10]:
                print(f"    parent not a title: {key[d]}({d}) -> {par[d]}")


if __name__ == "__main__":
    main()
