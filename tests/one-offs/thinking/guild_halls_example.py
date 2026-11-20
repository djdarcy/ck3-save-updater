"""One S1 row worked end to end: 1.20 guild halls through the game's 1.21 conversion and the carry.

For every city holding that has guild_halls_NN in the 1.20 witness (v17), prints counts; then for the chosen
province (argv 4, or the highest guild-halls tier in a city that is a county capital) prints the holding block
as it stands in each of the three saves, so the reader sees exactly what was there, what the conversion left,
and what the carry wrote.

Run: python -I -X utf8 tests/one-offs/thinking/guild_halls_example.py <v17> <game's 1.21 re-save of v17> <v19> [province]
Read-only: it opens the three saves and writes nothing.
"""
import collections
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator.savefile import read_save  # noqa: E402

GAME = pathlib.Path(r"E:/SteamLibrary/steamapps/common/Crusader Kings III/game")


def holdings(g: bytes) -> dict[str, bytes]:
    out = {}
    for e in gs.iter_entries(g, *gs.locate(g, "provinces").body):
        if not (e.key and e.key.isdigit()):
            continue
        h = re.search(rb"\n\t\tholding=\{", g[e.open:e.close])
        if h:
            at = e.open + h.end()
            out[e.key.decode()] = g[at - 1:gs.match_brace(g, at - 1) + 1]
    return out


def keys(hb: bytes) -> list[str]:
    return [k.decode() for k in re.findall(rb'type="?([^\s"}]+)', hb)]


def baronies() -> dict[str, str]:
    """province id -> barony key, from the 1.21 landed titles."""
    out = {}
    for f in sorted((GAME / "common" / "landed_titles").glob("*.txt")):
        text = f.read_text(encoding="utf-8-sig", errors="replace")
        for m in re.finditer(r"\b(b_[a-z_]+)\s*=\s*\{[^{}]*?\bprovince\s*=\s*(\d+)", text):
            out.setdefault(m.group(2), m.group(1))
    return out


def main(v17, conv, v19, pick=None):
    w, c, n = (holdings(read_save(p).gamestate) for p in (v17, conv, v19))
    names = baronies()
    with_gh = {p: hb for p, hb in w.items() if b"guild_halls_0" in hb}
    tiers = collections.Counter(k for hb in with_gh.values() for k in keys(hb) if k.startswith("guild_halls_"))
    print(f"1.20 holdings with guild halls: {len(with_gh)}; tiers {dict(sorted(tiers.items()))}")
    gone = sum(1 for p in with_gh if p in c and b"guild_halls" not in c[p])
    print(f"of those, the game's conversion kept guild halls in {sum(1 for p in with_gh if p in c and b'guild_halls' in c[p])},"
          f" dropped them in {gone}")
    in_guild = sum(1 for p in with_gh if p in n and b"guild_district" in n[p])
    print(f"after the carry (v19), holdings among them with a guild district: {in_guild}")
    if not pick:
        best = max(with_gh, key=lambda p: (max(int(t) for t in re.findall(rb"guild_halls_(\d\d)", with_gh[p])),
                                           len(with_gh[p])))
        pick = best
    print(f"\n=== province {pick} ({names.get(pick, '?')}) ===")
    for label, src in (("1.20 witness (v17)", w), ("the game's 1.21 conversion", c), ("after the carry (v19)", n)):
        print(f"\n--- {label} ---")
        print(src.get(pick, b"(no holding)").decode("utf-8", errors="replace"))


if __name__ == "__main__":
    main(*sys.argv[1:])
