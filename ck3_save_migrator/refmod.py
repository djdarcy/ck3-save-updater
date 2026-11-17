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
from collections.abc import Callable
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
    game_version: str = "1.20"    # the installed game's major.minor: supported_version and the description name it

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
    def group_key(self) -> str:
        # a bookmark in no group gets the game's plain "ungrouped" tab, with no stone frame (frontend_bookmarks.gui,
        # widget_ungrouped_bookmark_button; seen on 1.21.0, 2026-11-17); a group of its own gets the framed year tab
        return f"bm_group_ref_{self.stem}"

    @property
    def character_key(self) -> str:
        return f"bookmark_ref_{self.stem}_{self.character}"


def make_bookmark(*, date: str, character: int | str, title: str, culture: str, religion: str, house: str,
                  birth: str, female: bool = False, name: str = "",
                  government: str = "feudal_government", game_version: str | None = None) -> Bookmark:
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
    gv = ".".join((game_version or "1.20").split(".")[:2])     # "1.21.0" -> "1.21"
    if not re.fullmatch(r"\d+\.\d+", gv):
        raise RefModError(f"game version {game_version!r} is not a version like 1.21.0")
    return Bookmark(f"{y}.{mo}.{d}", int(character), title, culture, religion, house, f"{by}.{bmo}.{bd}",
                    female, name or f"Character {int(character)}", government, gv)


# --------------------------------------------------------------------------- the texts
def descriptor(b: Bookmark) -> str:
    return (f'version="0.1"\ntags={{\n\t"Utilities"\n}}\n'
            f'name="Ref Bookmark {b.date} (ck3update)"\nsupported_version="{b.game_version}.*"\n')


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
            f"\tgroup = {b.group_key}\n"
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


def bookmark_group(b: Bookmark) -> str:
    """The bookmark's own group (common/bookmarks/groups), so its tab is the game's framed year tab."""
    return (BOM + f"# The tab for the ck3update reference start at {b.date}.\n"
            f"{b.group_key} = {{\n"
            f"\tdefault_start_date = {b.date}\n"
            f"}}\n")


def localization(b: Bookmark) -> str:
    """The English localization, starting with the byte-order mark the game requires of a .yml file."""
    return (BOM + "l_english:\n"
            f' {b.group_key}: "Ref {b.date.split(".")[0]}"\n'
            f' {b.bookmark_key}: "Ref {b.date}"\n'
            f' {b.bookmark_key}_desc: "A plain {b.game_version} start on {b.date}, used as a reference save by '
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


# --------------------------------------------------------------------------- the names the game shows
NAMED_FLAGS = ("culture", "religion", "house", "title")
_TITLE_KEY = re.compile(r"^[ekdcb]_")


def name_tables(game_dir: Path) -> dict[str, dict[str, tuple]]:
    """For each named flag, game key -> (the key, the names the game shows for it), from ``<game_dir>/common`` and
    its localization (names.NameBook): cultures (common/culture/cultures), faiths as rites (common/religion/
    rite_types: 1.20's history files and bookmarks name the rite, insular_celtic, roman_rite), dynasty houses (their
    ``name``, alone and after their ``prefix``: "Briúin Seóla", "ua Briúin Seóla") and titles (every e_/k_/d_/c_/b_
    block of common/landed_titles)."""
    from . import history as H
    from .names import book
    bk = book(game_dir)
    shown = (lambda k: bk.display(k.strip('"'))) if bk else (lambda k: None)
    common = Path(game_dir) / "common"
    tables: dict[str, dict[str, tuple]] = {k: {} for k in NAMED_FLAGS}
    for key, body in H.read_folder(common / "culture" / "cultures"):
        if key and isinstance(body, list):
            tables["culture"][key] = (key, shown(key))
    for key, body in H.read_folder(common / "religion" / "rite_types"):
        if key and isinstance(body, list):
            tables["religion"][key] = (key, shown(key))
    for key, body in H.read_folder(common / "dynasty_houses"):
        if key and isinstance(body, list):
            f = {k: v for k, v in body if isinstance(v, str)}
            name = shown(f["name"]) if "name" in f else None
            pre = shown(f["prefix"]) if "prefix" in f else None
            tables["house"][key] = (key, name, f"{pre.strip()} {name}" if pre and name else None)

    def titles(pairs):
        for k, v in pairs:
            if k and isinstance(v, list) and _TITLE_KEY.match(k):
                tables["title"][k] = (k, shown(k))
                titles(v)
    titles(H.read_folder(common / "landed_titles"))
    return tables


def resolve_names(game_dir: Path | None, given: dict) -> tuple[dict, list[str]]:
    """``given`` with each of --culture/--religion/--house/--title turned into its game key: a key stays as it is, a
    name the game shows ("Insular Celtic", "Ireland") becomes its key, case, accents and punctuation ignored
    (names.norm). A name shared by several keys is refused with the candidates; an unknown one with the nearest
    names. Without the game's files only keys can be given. Returns (the flags, one line per name resolved)."""
    from .faith_lookup import LookupError_, _find
    named = {k: v for k, v in given.items() if k in NAMED_FLAGS}
    if not named:
        return dict(given), []
    if game_dir is None:
        bad = [f"--{k} {v!r}" for k, v in named.items() if not _KEY.match(v)]
        if bad:
            raise RefModError(f"{', '.join(bad)} is not a game key, and a name the game shows needs the game's files: "
                              "give --game-dir")
        return dict(given), []
    tables = name_tables(game_dir)
    out, notes = dict(given), []
    for k, v in named.items():
        t = tables[k]
        if not t:                                    # the folder is not there: leave the key as given
            continue
        try:
            key = _find({"religion": "faith"}.get(k, k), v, t, lambda it: it, hint=False,
                        label=lambda i, t=t: f"{next((n for n in t[i][1:] if n), i)} ({i})")
        except LookupError_ as exc:
            raise RefModError(f"--{k}: {exc}") from None
        if key != v:
            out[k] = key
            notes.append(f"--{k} {v!r} is {key}")
    return out, notes


def meta_date(meta: bytes) -> str:
    """The in-game date a save was made on, ``meta_date`` in its metadata."""
    m = re.search(rb"(?m)^\s*meta_date=\"?(-?\d+\.\d+\.\d+)\"?", meta)
    if not m:
        raise RefModError("the save's metadata has no meta_date")
    return m.group(1).decode()


def files(b: Bookmark, out: Path) -> dict[Path, str]:
    """Every file of the mod, path -> text: the folder's four files and the sibling ``.mod`` file."""
    folder = Path(out) / b.folder
    return {
        folder / "descriptor.mod": descriptor(b),
        folder / "common" / "bookmarks" / "bookmarks" / "zz_ref.txt": bookmark(b),
        folder / "common" / "bookmarks" / "groups" / "zz_ref_groups.txt": bookmark_group(b),
        folder / "localization" / "english" / "zz_ref_l_english.yml": localization(b),
        Path(out) / f"{b.folder}.mod": launcher_mod(b, folder),
    }


# The game's own bookmark art for the British Isles, copied from the player's install at write time (never shipped):
# the background of the 1066 "Hastings" bookmark, and its Scotland location picture. Without them the bookmark screen
# is white and the error log says "background ... not found" (measured on 1.21.0, 2026-11-17).
ART_BACKGROUND = "bm_1066_hastings.dds"
ART_LOCATION = "bm_1066_hastings_bookmark_hastings_scotland.dds"


def art(b: Bookmark, out: Path, game_dir: Path | None) -> dict[Path, Path]:
    """mod path -> the player's game file to copy: the bookmark background and the character's location picture,
    named as the game looks for them (``bm_<key>.dds``, ``bm_<key>_<character key>.dds``). Empty without the game's
    files, or when either picture is not in the install."""
    if game_dir is None:
        return {}
    src = Path(game_dir) / "gfx" / "interface" / "bookmarks"
    if not (src / ART_BACKGROUND).is_file() or not (src / ART_LOCATION).is_file():
        return {}
    dst = Path(out) / b.folder / "gfx" / "interface" / "bookmarks"
    return {dst / f"{b.bookmark_key}.dds": src / ART_BACKGROUND,
            dst / f"{b.bookmark_key}_{b.character_key}.dds": src / ART_LOCATION}


_OURS = re.compile(r'(?m)^name="[^"\n]*\(ck3update\)"\s*$')     # every name this module has written ends so


def _written_by_us(p: Path) -> bool:
    """A ``.mod`` file, or a mod folder by its ``descriptor.mod``, that names itself "... (ck3update)"."""
    f = p / "descriptor.mod" if p.is_dir() else p
    try:
        return bool(_OURS.search(f.read_text(encoding="utf-8", errors="replace")))
    except OSError:
        return False


def write_mod(b: Bookmark, out: Path, game_dir: Path | None = None, replace: bool = False,
              confirm: Callable[[list[Path]], bool] | None = None) -> list[Path]:
    """Write the mod into ``out``; refuse, before writing anything, if its folder or ``.mod`` file exists or
    ``out`` is not a folder. ``replace`` (``--force``, djdarcy 2026-11-17) lets an existing mod be written over: its
    files are written over in place and nothing is deleted. One that names itself "... (ck3update)" is taken as
    this command's and replaced at once. For any other, that name is the only evidence there is, so ``confirm`` is
    asked with the paths (djdarcy: "if we can't tell for certain we can just prompt with a Y/n"); without one (no
    terminal to answer from) it is refused, saying why. With the game's folder, also copy the bookmark's art from it
    (``art``). Returns the paths written."""
    out = Path(out)
    if not out.is_dir():
        raise RefModError(f"output folder does not exist: {out}")
    existing = [p for p in (out / b.folder, out / f"{b.folder}.mod") if p.exists()]
    if existing and not replace:
        raise RefModError(f"refusing to overwrite {existing[0]}: it already exists (--force replaces it)")
    unknown = [p for p in existing if not _written_by_us(p)]
    if unknown:
        if confirm is None:
            raise RefModError(f"refusing to overwrite {unknown[0]}: its name does not end in \"(ck3update)\", so it "
                              "may not be a mod reference-mod wrote, and there is no terminal to ask you from")
        if not confirm(unknown):
            raise RefModError(f"not overwritten: {unknown[0]} (you answered no)")
    written = []
    for path, text in files(b, out).items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
        written.append(path)
    for path, source in art(b, out, game_dir).items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(source.read_bytes())
        written.append(path)
    return written
