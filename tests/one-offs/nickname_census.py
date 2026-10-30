"""nickname_census: which characters' nicknames will 1.20 show, and with what text? (2026-10-30)

1.20 stores a character's nickname twice: the key (`nickname=nick_the_victorious`) and its rendered text
(`nickname_text="the Victorious"`); every character in the game's own 1.20 save carries nickname_text ("" when there
is no nickname). A 1.8.1 save has only the key, so migrated characters reach 1.20 without nickname_text, and the game
shows a garbled name (djdarcy: `Uilleam of " of Ireland`, `Echmarcach " of Ireland`).

This takes every nickname key on a save's characters and classifies it against the game folders and mods given:
defined in common/nicknames (1.20 game, then mods), English text in localization (1.20, mods, then the old game),
and the source that would supply nickname_text. Known answer: nick_the_tuatha_de_danann is defined in 1.20 vanilla
with the text "the Tuatha Dé Danann".

Usage: python -I tests/one-offs/nickname_census.py <save.ck3> --game <1.20 game dir> --old <old game dir>
                                                   [--mod <mod dir> ...]
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ck3_save_migrator import translate as T  # noqa: E402
from ck3_save_migrator.savefile import read_save  # noqa: E402

SECTIONS = ("living", "dead_unprunable", "characters/dead_prunable")
DEF = re.compile(r"^\s*(nick_[A-Za-z0-9_]+)\s*=", re.M)
LOC = re.compile(r'^\s*(nick_[A-Za-z0-9_]+):\d*\s*"(.*)"\s*$', re.M)


def defined(root: Path) -> set[str]:
    out = set()
    for f in (root / "common" / "nicknames").glob("*.txt") if (root / "common" / "nicknames").is_dir() else []:
        out |= set(DEF.findall(f.read_text(encoding="utf-8-sig", errors="replace")))
    return out


def english(root: Path) -> dict[str, str]:
    out = {}
    loc = root / "localization"
    if not loc.is_dir():
        return out
    for f in loc.rglob("*_l_english.yml"):
        for k, v in LOC.findall(f.read_text(encoding="utf-8-sig", errors="replace")):
            if not k.endswith("_desc"):
                out[k] = v
    return out


def main():
    a = sys.argv[1:]
    save = a[0]
    game = Path(a[a.index("--game") + 1])
    old = Path(a[a.index("--old") + 1])
    mods = [Path(a[i + 1]) for i, x in enumerate(a) if x == "--mod"]
    d_game, l_game = defined(game), english(game)
    d_mods, l_mods = set(), {}
    for m in mods:
        d_mods |= defined(m)
        l_mods.update(english(m))
    d_old, l_old = defined(old), english(old)
    assert "nick_the_tuatha_de_danann" in d_game and l_game.get("nick_the_tuatha_de_danann") == "the Tuatha Dé Danann", \
        "known answer failed: the method is broken"
    g = read_save(save).gamestate
    keys, total = Counter(), 0
    for sec in SECTIONS:
        for _, e in T.entries(g, sec):
            total += 1
            b = g[e.open:e.close]
            m = re.search(rb'\n\tnickname="?([A-Za-z0-9_]+)"?', b)
            if m and not re.search(rb"\n\tnickname_text=", b):
                keys[m.group(1).decode()] += 1
    classes = Counter()
    rows = []
    for k, n in keys.items():
        where = "1.20" if k in d_game else ("mod" if k in d_mods else ("old-only" if k in d_old else "nowhere"))
        text = l_game.get(k) or l_mods.get(k)
        src = "1.20 text" if k in l_game else ("mod text" if k in l_mods else ("old text" if k in l_old else "no text"))
        classes[(where, src)] += n
        rows.append((n, k, where, src, text or l_old.get(k) or ""))
    print(f"{total:,} characters; {sum(keys.values())} with a nickname and no nickname_text, {len(keys)} distinct keys")
    print("characters by (where the key is defined, where its English text comes from):")
    for c, n in classes.most_common():
        print(f"   {n:5d}  {c}")
    print("keys not defined in 1.20 (by characters):")
    for n, k, where, src, text in sorted(rows, reverse=True):
        if where != "1.20":
            print(f"   {n:4d}  {k:40s} {where:9s} {src:10s} {text[:50]}")


if __name__ == "__main__":
    main()
