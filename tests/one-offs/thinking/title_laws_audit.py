"""Title laws: which law GROUPS does every law-holding title in a fresh game cover, and which of ours miss one?

Goal 2026-11-20__16-02-08 S2, the remainder of the per-entity audit (DWP 2026-11-20__15-17-51 step 1; board U33).
Culture innovations are universal lists; laws are not (a realm holds one law per group), so the analogue is a group
that every law-holding reference title covers. Each law's group is read from the game's common/laws (a law key's
enclosing top-level block). Laws rarely move between groups across versions; a key with no group is reported.

Usage: python -I tests/one-offs/thinking/title_laws_audit.py <ref.ck3> <ours.ck3> [game_dir]
"""
import collections
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator.savefile import read_save  # noqa: E402

GAME = Path(r"E:\SteamLibrary\steamapps\common\Crusader Kings III\game")
LAWS = re.compile(rb"\n\tlaws=\{([^}]*)\}")  # an entry's own fields sit one tab in
KEY = re.compile(rb'"?([a-z_0-9]+)"?')


def law_groups(game: Path) -> dict[str, str]:
    out = {}
    for f in sorted((game / "common" / "laws").glob("*.txt")):
        t = re.sub(r"#[^\n]*", "", f.read_text(encoding="utf-8-sig", errors="replace"))
        depth, group = 0, None
        for m in re.finditer(r"([A-Za-z_0-9]+)\s*=\s*\{|\{|\}", t):
            if m.group(0) == "}":
                depth -= 1
                continue
            if depth == 0 and m.group(1):
                group = m.group(1)
            elif depth == 1 and m.group(1) and group:
                out.setdefault(m.group(1), group)
            depth += 1
    return out


def titles(g: bytes) -> dict[str, set[str]]:
    out = {}
    for e in gs.iter_entries(g, *gs.locate(g, "landed_titles/landed_titles").body):
        b = g[e.open:e.close]
        km = re.search(rb'\n\tkey="?([a-z_0-9]+)', b)
        lm = LAWS.search(b)
        if km and lm:
            out[km.group(1).decode()] = {k.decode() for k in KEY.findall(lm.group(1))}
    return out


def main(argv):
    groups = law_groups(Path(argv[2]) if len(argv) > 2 else GAME)
    ref, ours = (titles(read_save(p).gamestate) for p in argv[:2])
    for name, t in (("ref", ref), ("ours", ours)):
        unknown = collections.Counter(k for laws in t.values() for k in laws if k not in groups)
        print(f"{name}: {len(t)} law-holding titles; law keys with no group in the install: {dict(unknown) or 'none'}")

    def covered(laws):
        return {groups[k] for k in laws if k in groups}

    per_group = collections.Counter(gr for laws in ref.values() for gr in covered(laws))
    universal = sorted(gr for gr, n in per_group.items() if n == len(ref))
    print(f"groups every ref title covers ({len(universal)}): {universal}")
    short = collections.Counter(gr for laws in ours.values() for gr in universal if gr not in covered(laws))
    print(f"ours titles missing a universal group: {dict(short) or 'none'}")
    ex = [k for k, laws in ours.items() if any(gr not in covered(laws) for gr in universal)][:8]
    print("examples:", ex)
    # also: groups ours covers that ref never does, and per-group coverage rates side by side
    pg_ours = collections.Counter(gr for laws in ours.values() for gr in covered(laws))
    print("\ngroup: ref% / ours%")
    for gr in sorted(set(per_group) | set(pg_ours)):
        print(f"  {gr}: {100 * per_group[gr] / len(ref):.0f} / {100 * pg_ours[gr] / max(1, len(ours)):.0f}")


if __name__ == "__main__":
    main(sys.argv[1:])
