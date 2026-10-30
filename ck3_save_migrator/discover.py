"""Find the game and the player's saves on any machine, and read the versions of both.

The game: ``discover_games`` tries sources in order, keeps each candidate that is a game folder, drops repeats (by
resolved path) and returns ``GameInstall`` records, newest version first, each saying where it was found:

1. ``--game-dir`` or ``$CK3_GAME_DIR``: a folder that was named is used alone; one that is not a game folder is
   refused, never swapped for a discovered one; ``none`` means no game.
2. Steam's own record: on Windows the registry (``HKCU\\Software\\Valve\\Steam`` ``SteamPath``, else
   ``HKLM\\SOFTWARE\\WOW6432Node\\Valve\\Steam`` ``InstallPath``), read as a Steam root.
3. The usual Steam roots on each system.
4. On Windows, ``<drive>:\\SteamLibrary`` and ``<drive>:\\Steam`` on every drive that exists.
5. On Windows, the Xbox app (Game Pass): ``<drive>:\\XboxGames\\Crusader Kings III`` (or its ``Content``) on every
   drive marked with a ``.GamingRoot`` file (``xbox_games``; unverified on a real install).
6. The current folder, when it, or its ``game`` child, is a game folder.

A Steam root is read through its ``steamapps/libraryfolders.vdf``, which lists every library; the library whose
``apps`` names CK3's app id (1158310), or that has CK3's app manifest, holds the game, in
``steamapps/common/<installdir>/game``. A game folder is valid when ``common/landed_titles`` is a folder in it; its
version is ``rawVersion`` in ``launcher/launcher-settings.json`` beside it (None when that cannot be read).

The saves: ``save_games_dir`` is the game's ``save games`` folder (on Windows under the Documents known folder,
which may be redirected, e.g. to OneDrive, so never assumed to be ``~/Documents``); ``find_save`` takes a path, or
the name of a save in that folder. ``save_versions`` reads a save's versions from its metadata.

``registry``, ``drives``, ``home``, ``cwd`` and ``system`` are parameters so tests never touch the real registry
or disks.
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

CK3_APP_ID = "1158310"
DEFAULT_INSTALLDIR = "Crusader Kings III"
REG_STEAM_PATHS = (r"HKCU\Software\Valve\Steam\SteamPath", r"HKLM\SOFTWARE\WOW6432Node\Valve\Steam\InstallPath")


@dataclass(frozen=True)
class GameInstall:
    source: str              # where it was found, in words
    path: Path               # the 'game' folder
    version: str | None      # rawVersion from the launcher settings; None when they cannot be read

    @property
    def install(self) -> Path:
        """The folder that holds 'game', 'binaries' and 'launcher'."""
        return self.path.parent


# --------------------------------------------------------------------------- versions
def parse_version(text: str | None) -> tuple[int, ...] | None:
    """The leading dotted numbers of a version ("1.20.1.2 (Crozier)" -> (1, 20, 1, 2)); None when there are none."""
    m = re.match(r"\s*v?(\d+(?:\.\d+)*)", text or "")
    return tuple(int(x) for x in m.group(1).split(".")) if m else None


def compare_versions(a: str | None, b: str | None) -> int | None:
    """-1, 0 or 1 as ``a`` is older than, the same as, or newer than ``b``; missing parts count as 0
    ("1.20" == "1.20.0"); None when either has no version number."""
    pa, pb = parse_version(a), parse_version(b)
    if pa is None or pb is None:
        return None
    n = max(len(pa), len(pb))
    pa, pb = pa + (0,) * (n - len(pa)), pb + (0,) * (n - len(pb))
    return (pa > pb) - (pa < pb)


def game_version(game: Path) -> str | None:
    """``rawVersion`` from ``<install>/launcher/launcher-settings.json`` (``game`` is the 'game' folder)."""
    try:
        data = json.loads((Path(game).parent / "launcher" / "launcher-settings.json").read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    v = data.get("rawVersion") if isinstance(data, dict) else None
    return v if isinstance(v, str) and v.strip() else None


_META_FIELD = re.compile(rb'(?m)^\t(version|save_game_version|portraits_version)="?([^"\s]*)"?\s*$')


def save_versions(meta: bytes) -> dict:
    """``{"version", "save_game_version", "portraits_version"}`` from a save's metadata block; a field the
    metadata does not have is None. ``version`` is a string ("1.8.1"), the other two are numbers."""
    out: dict = {"version": None, "save_game_version": None, "portraits_version": None}
    for key, val in _META_FIELD.findall(meta):
        k, v = key.decode(), val.decode("utf-8", "replace")
        if out[k] is not None:
            continue                        # the first one, at depth 1 of meta_data
        out[k] = v if k == "version" else (int(v) if v.isdigit() else None)
    return out


# --------------------------------------------------------------------------- Valve KeyValues (libraryfolders.vdf)
_VDF_TOKEN = re.compile(r'"((?:[^"\\]|\\.)*)"|([{}])|//[^\n]*|([^\s{}"]+)', re.S)
_VDF_ESCAPES = {"\\\\": "\\", '\\"': '"', "\\n": "\n", "\\t": "\t"}


def parse_vdf(text: str) -> dict:
    """Valve's KeyValues text as nested dicts: ``"key" "value"`` pairs and ``"key" { ... }`` blocks, ``//``
    comments ignored, a repeated key's last value kept. Unbalanced braces end the read without raising."""
    tokens = []
    for m in _VDF_TOKEN.finditer(text):
        if m.group(1) is not None:
            tokens.append(("s", re.sub(r"\\[\\\"nt]", lambda e: _VDF_ESCAPES[e.group(0)], m.group(1))))
        elif m.group(2):
            tokens.append((m.group(2), None))
        elif m.group(3):
            tokens.append(("s", m.group(3)))
    root: dict = {}
    stack = [root]
    key = None
    for kind, val in tokens:
        if kind == "}":
            if len(stack) > 1:
                stack.pop()
            key = None
        elif kind == "{":
            child: dict = {}
            if key is not None:
                stack[-1][key] = child
            stack.append(child)
            key = None
        elif key is None:
            key = val
        else:
            stack[-1][key] = val
            key = None
    return root


def _read_vdf(path: Path) -> dict:
    try:
        return parse_vdf(path.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return {}


def steam_libraries(steam_root: Path) -> list[tuple[Path, set[str]]]:
    """(library folder, the app ids its ``apps`` block names) for every library ``libraryfolders.vdf`` lists, the
    Steam root itself first. Both layouts are read: ``"1" { "path" "..." "apps" {...} }`` and the older
    ``"1" "<library path>"``."""
    out = [(Path(steam_root), set())]
    vdf = _read_vdf(Path(steam_root) / "steamapps" / "libraryfolders.vdf")
    folders = next((v for k, v in vdf.items() if k.lower() == "libraryfolders" and isinstance(v, dict)), {})
    for key, val in folders.items():
        if isinstance(val, dict) and isinstance(val.get("path"), str):
            apps = val.get("apps")
            out.append((Path(val["path"]), set(apps) if isinstance(apps, dict) else set()))
        elif key.isdigit() and isinstance(val, str):
            out.append((Path(val), set()))
    return out


def is_game_dir(path: Path) -> bool:
    return (Path(path) / "common" / "landed_titles").is_dir()


def game_in_library(library: Path) -> Path | None:
    """The 'game' folder of CK3 in one Steam library: the app manifest's ``installdir``, else the usual name."""
    manifest = _read_vdf(Path(library) / "steamapps" / f"appmanifest_{CK3_APP_ID}.acf")
    state = next((v for k, v in manifest.items() if k.lower() == "appstate" and isinstance(v, dict)), {})
    installdir = state.get("installdir") if isinstance(state.get("installdir"), str) else DEFAULT_INSTALLDIR
    game = Path(library) / "steamapps" / "common" / installdir / "game"
    return game if is_game_dir(game) else None


def games_under_steam_root(steam_root: Path) -> list[tuple[Path, str]]:
    """(game folder, which library) for every library of a Steam root that holds CK3; the libraries whose
    ``apps`` name CK3 come first, then any other with the app manifest or the game folder."""
    libs = steam_libraries(steam_root)
    named = [lib for lib, apps in libs if CK3_APP_ID in apps]
    rest = [lib for lib, apps in libs if CK3_APP_ID not in apps]
    out = []
    for lib in named + rest:
        game = game_in_library(lib)
        if game is not None:
            how = "its library list names the game" if lib in named else "found by its folders"
            out.append((game, f"library {lib.as_posix()} ({how})"))
    return out


# --------------------------------------------------------------------------- where Steam is
def windows_registry() -> dict[str, str]:
    """The Steam values of ``REG_STEAM_PATHS`` this machine's registry holds (empty off Windows)."""
    if sys.platform != "win32":
        return {}
    import winreg
    hives = {"HKCU": winreg.HKEY_CURRENT_USER, "HKLM": winreg.HKEY_LOCAL_MACHINE}
    out = {}
    for full in REG_STEAM_PATHS:
        hive, rest = full.split("\\", 1)
        key, name = rest.rsplit("\\", 1)
        try:
            with winreg.OpenKey(hives[hive], key) as k:
                val, _ = winreg.QueryValueEx(k, name)
        except OSError:
            continue
        if isinstance(val, str) and val:
            out[full] = val
    return out


def windows_drives() -> list[str]:
    """``C:\\``, ``D:\\``, ... for every drive letter that exists (empty off Windows)."""
    if sys.platform != "win32":
        return []
    return [f"{c}:\\" for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" if os.path.exists(f"{c}:\\")]


def default_steam_roots(system: str, home: Path) -> list[Path]:
    if system == "win32":
        return [Path(r"C:\Program Files (x86)\Steam")]
    return [home / ".steam" / "steam", home / ".local" / "share" / "Steam",
            home / "Library" / "Application Support" / "Steam"]


XBOX_FOLDER = "XboxGames"
XBOX_TITLE = "Crusader Kings III"


def xbox_games(drive: Path) -> list[Path]:
    """CK3 installed by the Xbox app (Game Pass) on one drive. UNVERIFIED on a real install: the layout comes from
    public descriptions of the Xbox app, not from a machine that has the game this way.

    The Xbox app marks each drive it may install to with a hidden ``.GamingRoot`` file at the drive's root and
    installs into ``XboxGames`` beside it, games often under a ``Content`` folder. ``.GamingRoot``'s binary content
    is not read (its format is not documented), so the default folder name is assumed. A drive without that file
    is not looked at. Each guess passes the same game-folder test as every other source, so a wrong guess finds
    nothing rather than a wrong folder."""
    if not (Path(drive) / ".GamingRoot").is_file():
        return []
    base = Path(drive) / XBOX_FOLDER / XBOX_TITLE
    out = []
    for cand in (base / "Content", base, base / "Content" / "game", base / "game"):
        if is_game_dir(cand) and cand not in out:
            out.append(cand)
    return out


# --------------------------------------------------------------------------- the game
def discover_games(explicit: str | None = None, env: str | None = None, *, registry: dict | None = None,
                   drives: list | None = None, home: Path | None = None, cwd: Path | None = None,
                   system: str | None = None) -> list[GameInstall]:
    """Every CK3 install found, newest version first (an unknown version last), each with its source.

    ``explicit`` is ``--game-dir``; ``env`` is ``$CK3_GAME_DIR`` (read from the environment when not given). A
    folder named by either is the only one returned; one that is not a game folder raises FileNotFoundError;
    ``none`` returns an empty list."""
    if env is None:
        env = os.environ.get("CK3_GAME_DIR")
    given, source = (explicit, "--game-dir") if explicit is not None else (env, "$CK3_GAME_DIR")
    if given:
        if given.strip().lower() == "none":
            return []
        p = Path(given).expanduser()
        if not is_game_dir(p):
            # a folder that was named but is not a game folder is refused, never swapped for a discovered one
            raise FileNotFoundError(f"{source.lstrip('$')} {given} is not the game's 'game' folder "
                                    f"(expected {p / 'common' / 'landed_titles'})")
        return [GameInstall(source, p, game_version(p))]

    system = system or sys.platform
    home = Path(home) if home is not None else Path.home()
    cwd = Path(cwd) if cwd is not None else Path.cwd()
    registry = windows_registry() if registry is None else registry
    drives = windows_drives() if drives is None else drives

    found: list[tuple[str, Path]] = []
    for name in REG_STEAM_PATHS:
        if registry.get(name):
            label = name.rsplit("\\", 1)[1]
            found += [(f"Steam ({label} in the registry), {lib}", g) for g, lib in
                      games_under_steam_root(Path(registry[name]))]
    for root in default_steam_roots(system, home):
        found += [(f"Steam at {root.as_posix()}, {lib}", g) for g, lib in games_under_steam_root(root)]
    for drive in drives:
        for folder in ("SteamLibrary", "Steam"):
            root = Path(drive) / folder
            found += [(f"{root.as_posix()} on a drive, {lib}", g) for g, lib in games_under_steam_root(root)]
    for drive in drives:
        found += [("Xbox app (Game Pass)", g) for g in xbox_games(Path(drive))]
    for cand in (cwd, cwd / "game"):
        if is_game_dir(cand):
            found.append(("the current folder", cand))

    seen, out = set(), []
    for src, game in found:
        try:
            key = os.path.normcase(str(game.resolve()))
        except OSError:
            key = os.path.normcase(str(game))
        if key in seen:
            continue
        seen.add(key)
        out.append(GameInstall(src, game, game_version(game)))
    # newest first; installs without a readable version after those with one, in discovery order
    order = sorted(range(len(out)), key=lambda i: (parse_version(out[i].version) is None,
                                                   tuple(-x for x in parse_version(out[i].version) or ()), i))
    return [out[i] for i in order]


# --------------------------------------------------------------------------- the saves
def documents_dir() -> Path | None:
    """Windows' Documents known folder (SHGetKnownFolderPath), wherever it is redirected; None when it cannot be
    read, and off Windows."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes
        from uuid import UUID

        class GUID(ctypes.Structure):
            _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD),
                        ("Data4", ctypes.c_ubyte * 8)]

        u = UUID("{FDD39AD0-238F-46AF-ADB4-6C85480369C7}")       # FOLDERID_Documents
        guid = GUID(u.fields[0], u.fields[1], u.fields[2], (ctypes.c_ubyte * 8).from_buffer_copy(u.bytes[8:]))
        out = ctypes.c_wchar_p()
        if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(out)) != 0:
            return None
        try:
            return Path(out.value) if out.value else None
        finally:
            ctypes.windll.ole32.CoTaskMemFree(out)
    except (OSError, AttributeError, ValueError):
        return None


GAME_DOCS = Path("Paradox Interactive") / "Crusader Kings III"


def game_documents_dir(*, system: str | None = None, home: Path | None = None,
                       documents: Path | None = None) -> Path | None:
    """The game's own documents folder (it holds ``save games``, ``mod`` and the logs)."""
    system = system or sys.platform
    home = Path(home) if home is not None else Path.home()
    if system == "win32":
        documents = documents if documents is not None else documents_dir()
        return documents / GAME_DOCS if documents is not None else None
    if system == "darwin":
        return home / "Documents" / GAME_DOCS
    return home / ".local" / "share" / GAME_DOCS


def save_games_dir(**kw) -> Path | None:
    """The game's ``save games`` folder (see ``game_documents_dir`` for the keywords); None when the documents
    folder cannot be found."""
    docs = game_documents_dir(**kw)
    return docs / "save games" if docs is not None else None


def find_save(name_or_path: str, *, folder: Path | None = None, **kw) -> Path:
    """A path to an existing file, as it is; otherwise a save in the ``save games`` folder (``folder``, else
    ``save_games_dir(**kw)``) named exactly that, with or without ``.ck3``, case ignored. FileNotFoundError when
    there is none; ValueError, listing them, when there are several."""
    p = Path(name_or_path).expanduser()
    if p.is_file():
        return p
    folder = folder if folder is not None else save_games_dir(**kw)
    if folder is None or not Path(folder).is_dir():
        where = f"no save folder at {folder}" if folder is not None else "the save folder could not be found"
        raise FileNotFoundError(f"no such save: {name_or_path} (not a file, and {where})")
    want = {p.name.lower(), p.name.lower() + ".ck3"}
    hits = sorted(f for f in Path(folder).iterdir() if f.is_file() and f.name.lower() in want)
    if not hits:
        raise FileNotFoundError(f"no such save: {name_or_path} (not a file, and not in {folder})")
    if len(hits) > 1:
        raise ValueError(f"{name_or_path} names more than one save in {folder}: "
                         + ", ".join(h.name for h in hits) + "; give the full name or path")
    return hits[0]
