"""Write a names-only old-map table from a game's own landed_titles, for R15's built-in old map.

A table keeps exactly what R15 reads from an old game (``deadtitles.title_tree``): every title key, its place in
the de jure tree (each title nested in its parent), and each barony's ``province``. Nothing else: no colours,
cultural names, history or capitals. R15 reads the table as it reads the game's own folder, so a player without the
old game still has removed and moved titles settled (djdarcy 2026-11-07: "giving people titles from a moment in
time. But it's better than most players being stuck"). Design: 2026-11-07 19:52, built-in old-map table.

Usage:
    python scripts/title_table.py <game folder> <out folder> --version 1.8.2 --game-line 1.8
        [--name "Crusader Kings III"] [--source "where the game was read"]

The out folder gets ``common/landed_titles/00_landed_titles.txt`` and ``table.toml`` (the provenance). The written
file is read back and must give the same tree as the game's folder, or nothing is kept.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ck3_save_migrator.deadtitles import title_tree  # noqa: E402

HEADER = ("# Names only, written by scripts/title_table.py: each title key, nested in its de jure parent, and each\n"
          "# barony's province, as R15 reads them. No colours, cultural names, history or capitals.\n")


def render(parent: dict[str, str | None], province: dict[str, int]) -> str:
    children: dict[str | None, list[str]] = {}
    for key, up in parent.items():                     # dict order is the game's own order
        children.setdefault(up, []).append(key)
    out = [HEADER]

    def emit(key: str, depth: int) -> None:
        pad = "\t" * depth
        out.append(f"{pad}{key} = {{\n")
        if key in province:
            out.append(f"{pad}\tprovince = {province[key]}\n")
        for child in children.get(key, []):
            emit(child, depth + 1)
        out.append(f"{pad}}}\n")
    for top in children.get(None, []):
        emit(top, 0)
    return "".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("game", type=Path, help="the old game's 'game' folder (holding common/landed_titles)")
    ap.add_argument("out", type=Path, help="the table folder to write, e.g. ck3_save_migrator/known_titles/vanilla_1.8.2")
    ap.add_argument("--version", required=True)
    ap.add_argument("--game-line", required=True, help="the version line(s) the table stands for, e.g. 1.8")
    ap.add_argument("--name", default="Crusader Kings III")
    ap.add_argument("--source", default="")
    a = ap.parse_args(argv)
    src = a.game / "common" / "landed_titles"
    parent, province = title_tree(src)
    dest = a.out / "common" / "landed_titles"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "00_landed_titles.txt").write_text(render(parent, province), encoding="utf-8", newline="\n")
    if title_tree(dest) != (parent, province):
        (dest / "00_landed_titles.txt").unlink()
        print("the written table does not read back as the game's tree; nothing kept", file=sys.stderr)
        return 1
    source = a.source or f"the game's {a.version} common/landed_titles"
    (a.out / "table.toml").write_text(
        f'name = "{a.name}"\nversion = "{a.version}"\ngame_line = "{a.game_line}"\nsource = "{source}"\n',
        encoding="utf-8", newline="\n")
    print(f"wrote {dest / '00_landed_titles.txt'}: {len(parent):,} titles, {len(province):,} baronies")
    return 0


if __name__ == "__main__":
    sys.exit(main())
