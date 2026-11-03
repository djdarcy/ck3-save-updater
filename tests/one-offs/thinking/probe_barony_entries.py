"""Print each named title's entry from the gamestate of one or more .ck3 saves, plus the save's mod list size.

Probe for the 0.4.0 sweep's H1 finding (2026-11-02): b_bailjar and b_wuluhai lint as capital baronies with no
county above them in the founding save's update without the play6 recipe, and not with it.

    python -I tests/one-offs/thinking/probe_barony_entries.py <save.ck3> [<save.ck3> ...] --keys b_bailjar,b_wuluhai
"""
import argparse
import re
import zipfile
from pathlib import Path


def gamestate(path: Path) -> bytes:
    with zipfile.ZipFile(path) as z:
        return z.read("gamestate")


def entry(gs: bytes, key: str) -> str:
    m = re.search(rb'\bkey="?' + re.escape(key.encode()) + rb'"?\s', gs)
    if not m:
        return "(absent)"
    start = gs.rfind(b"\n\t", 0, m.start())          # the title's own line: "\t<id>={"
    depth, i = 0, gs.index(b"{", start)
    for j in range(i, min(len(gs), i + 20000)):
        depth += {123: 1, 125: -1}.get(gs[j], 0)
        if depth == 0:
            return gs[start:j + 1].decode("utf-8", "replace").strip()
    return gs[start:start + 2000].decode("utf-8", "replace")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("saves", nargs="+", type=Path)
    ap.add_argument("--keys", required=True)
    a = ap.parse_args()
    for s in a.saves:
        gs = gamestate(s)
        mods = re.search(rb"\bmods=\{([^}]*)\}", gs[:200000])
        print(f"=== {s.name}: {len(mods.group(1).split()) if mods else '?'} mod tokens in the head")
        for k in a.keys.split(","):
            print(f"--- {k}")
            print(entry(gs, k))
        print()


if __name__ == "__main__":
    main()
