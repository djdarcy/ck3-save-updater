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
    # UTF-8 with a byte-order mark: the game logs every script file without one ("should be in utf8-bom encoding")
    return (BOM + f"# Reference start at {b.date} for ck3update.\n"
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


# --------------------------------------------------------------------------- picking the ruler from the history files
# kingdoms and duchies first (a playable, well-defined realm), then empires, counties, baronies
TIER_RANK = {"k": 0, "d": 1, "e": 2, "c": 3, "b": 4}
ADULT = 16


@dataclass(frozen=True)
class Pick:
    """A ruler chosen from the game's history files, with the bookmark fields read from them."""
    character: str
    title: str
    culture: str | None
    religion: str | None
    house: str | None
    birth: str | None
    female: bool
    name: str
    government: str
    house_how: str                # how the house was found (dynasty_house, or the dynasty's main house)
    why: str


REQUIRED = ("culture", "religion", "house", "birth")


def _ruler_fields(c, title: str, rows: list, date, houses: dict) -> dict:
    """The bookmark's fields from a character's history as of ``date``. The faith is ``rite`` (1.20's history
    files), else ``religion`` or ``faith`` (older games); the house is ``dynasty_house``, else the main house of the
    character's ``dynasty`` id, from common/dynasty_houses."""
    from . import history as H
    now = c.as_of(date)
    birth = ".".join(map(str, c.birth)) if c.birth else None
    house, how = now.get("dynasty_house"), "dynasty_house in the character's history"
    if not house:
        house, how = H.main_house(houses, now.get("dynasty"))
    return {"culture": now.get("culture"), "religion": now.get("rite") or now.get("religion") or now.get("faith"),
            "house": house, "house_how": how, "birth": birth, "female": now.get("female") == "yes",
            "name": now.get("name", ""), "government": H.as_of(rows, "government", date) or "feudal_government"}


def _missing(f: dict) -> list[str]:
    return [k if k != "religion" else "faith" for k in REQUIRED if not f[k]]


def pick_ruler(game_dir: Path, date: str, character: str | None = None) -> Pick:
    """A character alive on ``date`` who holds a title on it, read from ``<game_dir>/history``.

    With ``character``, that character (refused when not alive and holding on the date; fields the history lacks
    come back None, for the caller to refuse or take from flags). Otherwise only candidates whose culture, faith,
    dynasty house and birth date are all found; among them: adult (16 or older) first, the highest-ranked title
    held (kingdom, duchy, empire, county, barony), then the title key, so the pick is the same every run. When no
    living holder has all four, RefModError names what the first one lacked: an incomplete ruler is never picked.
    Only numeric history ids are candidates (the bookmark names the character by its history id)."""
    from . import history as H
    y, mo, d = parse_date(date)
    when = (y, mo, d)
    hist = Path(game_dir) / "history"
    if not (hist / "characters").is_dir() or not (hist / "titles").is_dir():
        raise RefModError(f"no history folders in {game_dir} (expected history/characters and history/titles)")
    chars = H.characters(hist / "characters")
    trows = H.titles(hist / "titles")
    held = H.holders(trows, when)
    houses = H.dynasty_houses(Path(game_dir) / "common" / "dynasty_houses")

    def best_title(cid: str) -> str:
        return min(held[cid], key=lambda t: (TIER_RANK.get(t[:1], 9), t))

    if character is not None:
        cid = str(character)
        c = chars.get(cid)
        if c is None:
            raise RefModError(f"character {cid} is not in {hist / 'characters'}")
        if not c.alive_on(when):
            raise RefModError(f"character {cid} is not alive on {date} (born {c.birth}, died {c.death})")
        if cid not in held:
            raise RefModError(f"character {cid} holds no title on {date} in {hist / 'titles'}")
        t = best_title(cid)
        f = _ruler_fields(c, t, trows[t], when, houses)
        return Pick(cid, t, **f, why=f"the character given with --character; house: {f['house_how']}")

    living, ranked = 0, []
    closest = None
    for cid, ts in held.items():
        c = chars.get(cid)
        if c is None or not cid.isdigit() or not c.alive_on(when):
            continue
        living += 1
        t = best_title(cid)
        f = _ruler_fields(c, t, trows[t], when, houses)
        adult = (c.age_on(when) or 0) >= ADULT
        key = (not adult, TIER_RANK.get(t[:1], 9), t)
        if _missing(f):
            # never written: a bookmark needs every one of the four; kept only to say what was missing
            if closest is None or key < closest[0]:
                closest = (key, cid, t, _missing(f))
            continue
        ranked.append((key, cid, t, f, adult))
    if not living:
        raise RefModError(f"no character in {hist} is alive and holds a title on {date}")
    if not ranked:
        _, cid, t, miss = closest
        raise RefModError(f"none of the {living} living title holders on {date} has culture, faith, house and birth "
                          f"all found in the history (the first, character {cid} holding {t}, has no "
                          f"{', '.join(miss)}); give the ruler with --character and the missing flags")
    ranked.sort(key=lambda r: r[0])
    _, cid, t, f, adult = ranked[0]
    why = (f"alive and holding {t} on {date}; of the {len(ranked)} living title holders with culture, faith, house "
           f"and birth found, the first {'adult, ' if adult else '(none is adult), '}holding the highest-ranked "
           f"title (kingdom, duchy, empire, county, barony), then by title key; house: {f['house_how']}")
    return Pick(cid, t, **f, why=why)


def meta_date(meta: bytes) -> str:
    """The in-game date a save was made on, ``meta_date`` in its metadata."""
    m = re.search(rb"(?m)^\s*meta_date=\"?(-?\d+\.\d+\.\d+)\"?", meta)
    if not m:
        raise RefModError("the save's metadata has no meta_date")
    return m.group(1).decode()


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
