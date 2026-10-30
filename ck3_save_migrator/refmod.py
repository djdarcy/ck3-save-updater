"""Write a small local bookmark mod that starts a 1.20 game on a chosen date, to make a reference save from.

The new-map rules (R14-R16) copy the regions 1.20 added from a "reference": a save of a fresh 1.20 game at the
campaign's own date. The game's bookmarks start only on a few fixed dates, so a player makes a bookmark for their
date, starts a game from it, and saves at once. This module produces that mod's files.

The texts are pure functions (``descriptor``, ``bookmark``, ``localization``, ``launcher_mod``); ``write_mod``
writes them, refusing to overwrite anything. The format follows the game's own bookmarks: one bookmark with one
playable character, whose block names the character's history id, title, culture, religion, government,
difficulty, birth, type, dynasty house, dynasty splendor level and position on the bookmark screen.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

BOM = "﻿"
# the game's calendar has no leap years
_DAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
_DATE = re.compile(r"^(\d{1,4})\.(\d{1,2})\.(\d{1,2})$")
_KEY = re.compile(r"^[A-Za-z0-9_\-']+$")


class RefModError(ValueError):
    """A reference mod cannot be written: a bad option, or a file that already exists."""


def parse_date(text: str) -> tuple[int, int, int]:
    """``"987.10.27"`` -> (987, 10, 27). The game writes dates as year.month.day without leading zeros; leading
    zeros are accepted here and dropped. Refused: any other shape, month outside 1-12, day outside the month."""
    m = _DATE.match(text.strip())
    if not m:
        raise RefModError(f"date {text!r} is not YYYY.M.D (for example 987.10.27)")
    y, mo, d = (int(x) for x in m.groups())
    if not 1 <= mo <= 12:
        raise RefModError(f"date {text!r}: month {mo} is not 1-12")
    if not 1 <= d <= _DAYS[mo - 1]:
        raise RefModError(f"date {text!r}: day {d} is not in month {mo} (1-{_DAYS[mo - 1]})")
    return y, mo, d


@dataclass(frozen=True)
class Bookmark:
    """What the bookmark mod says. ``date`` is normalised (no leading zeros)."""
    date: str
    character: int                # the character's history id (game/history/characters)
    title: str                    # a title the character holds on the date (game/history/titles)
    culture: str
    religion: str                 # in 1.20 the bookmark's religion key is a faith key (insular_celtic, ...)
    house: str                    # the dynasty house key (house_..., in common/dynasty_houses)
    birth: str
    female: bool = False
    name: str = ""                # shown on the bookmark screen; defaults to "Character <id>"
    government: str = "feudal_government"

    @property
    def stem(self) -> str:
        return self.date.replace(".", "_")

    @property
    def folder(self) -> str:
        return f"zz_ref_{self.stem}"

    @property
    def bookmark_key(self) -> str:
        return f"bm_{self.stem}"

    @property
    def character_key(self) -> str:
        return f"bookmark_ref_{self.stem}_{self.character}"


def make_bookmark(*, date: str, character: int | str, title: str, culture: str, religion: str, house: str,
                  birth: str, female: bool = False, name: str = "",
                  government: str = "feudal_government") -> Bookmark:
    """A checked ``Bookmark``: both dates parse, the history id is a number, the keys are game keys."""
    y, mo, d = parse_date(date)
    by, bmo, bd = parse_date(birth)
    if (by, bmo, bd) > (y, mo, d):
        raise RefModError(f"birth {birth} is after the bookmark date {date}")
    if not str(character).isdigit():
        raise RefModError(f"character {character!r} is not a history id (a number, as in game/history/characters)")
    for label, key in (("title", title), ("culture", culture), ("religion", religion), ("house", house),
                       ("government", government)):
        if not _KEY.match(key or ""):
            raise RefModError(f"{label} {key!r} is not a game key")
    if '"' in name or "\n" in name:
        raise RefModError("name may not contain a double quote or a line break")
    return Bookmark(f"{y}.{mo}.{d}", int(character), title, culture, religion, house, f"{by}.{bmo}.{bd}",
                    female, name or f"Character {int(character)}", government)


# --------------------------------------------------------------------------- the texts
def descriptor(b: Bookmark) -> str:
    return (f'version="0.1"\ntags={{\n\t"Utilities"\n}}\n'
            f'name="Reference bookmark {b.date} (ck3update)"\nsupported_version="1.20.*"\n')


def launcher_mod(b: Bookmark, folder: Path) -> str:
    """The ``<folder>.mod`` file the launcher reads: the descriptor plus the mod folder's absolute path."""
    return descriptor(b) + f'path="{Path(folder).resolve().as_posix()}"\n'


def bookmark(b: Bookmark) -> str:
    return (f"# Reference start at {b.date} for ck3update.\n"
            f"# Played as character {b.character}, holder of {b.title}; game/history/characters and\n"
            f"# game/history/titles must have them alive and holding it on this date.\n"
            f"{b.bookmark_key} = {{\n"
            f"\tstart_date = {b.date}\n"
            f"\tis_playable = yes\n"
            f"\tweight = {{\n\t\tvalue = 0\n\t}}\n"
            f"\tcharacter = {{\n"
            f"\t\tname = {b.character_key}\n"
            f"\t\thistory_id = {b.character}\n"
            f"\t\ttitle = {b.title}\n"
            f"\t\tculture = {b.culture}\n"
            f"\t\treligion = {b.religion}\n"
            f"\t\tgovernment = {b.government}\n"
            f'\t\tdifficulty = "BOOKMARK_CHARACTER_DIFFICULTY_MEDIUM"\n'
            f"\t\tbirth = {b.birth}\n"
            f"\t\ttype = {'female' if b.female else 'male'}\n"
            f"\t\tdynasty_house = {b.house}\n"
            f"\t\tdynasty_splendor_level = 1\n"
            f"\t\tposition = {{ 400 300 }}\n"
            f"\t}}\n"
            f"}}\n")


def localization(b: Bookmark) -> str:
    """The English localization, starting with the byte-order mark the game requires of a .yml file."""
    return (BOM + "l_english:\n"
            f' {b.bookmark_key}: "{b.date} Reference (ck3update)"\n'
            f' {b.bookmark_key}_desc: "A plain 1.20 start on {b.date}, used as a reference save by '
            f'ck3update."\n'
            f' {b.character_key}: "{b.name}"\n'
            f' {b.character_key}_desc: "Reference start for ck3update."\n'
            f' {b.character_key}_subheading: "$BOOKMARK_SUBHEADING_DEFAULT$"\n')


def files(b: Bookmark, out: Path) -> dict[Path, str]:
    """Every file of the mod, path -> text: the folder's three files and the sibling ``.mod`` file."""
    folder = Path(out) / b.folder
    return {
        folder / "descriptor.mod": descriptor(b),
        folder / "common" / "bookmarks" / "bookmarks" / "zz_ref.txt": bookmark(b),
        folder / "localization" / "english" / "zz_ref_l_english.yml": localization(b),
        Path(out) / f"{b.folder}.mod": launcher_mod(b, folder),
    }


def write_mod(b: Bookmark, out: Path) -> list[Path]:
    """Write the mod into ``out``; refuse, before writing anything, if its folder or ``.mod`` file exists or
    ``out`` is not a folder. Returns the paths written."""
    out = Path(out)
    if not out.is_dir():
        raise RefModError(f"output folder does not exist: {out}")
    for p in (out / b.folder, out / f"{b.folder}.mod"):
        if p.exists():
            raise RefModError(f"refusing to overwrite {p}: it already exists")
    written = []
    for path, text in files(b, out).items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
        written.append(path)
    return written
