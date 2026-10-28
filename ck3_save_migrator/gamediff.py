"""What a game update changed: two CK3 ``game`` folders compared by definition, and what of it a save uses.

Read only. The definition files are every ``.txt`` under ``common/``, ``events/`` and ``history/``, and
``map_data/definition.csv``. Each file is read as script (``#`` comments dropped, strings kept whole) and split into
its top-level definitions, ``key = value`` or ``key = { ... }``; a definition's body is compared as its token list,
so a change of whitespace, of comments or of line breaks is not a change. ``@name`` constants and ``namespace``
lines are file plumbing, not definitions, and are left out. Definitions are grouped by the folder their file is in;
a key that moves between files of one folder is not a change.

Three kinds of definition sit below the top level and are listed as their own groups:

* every landed title (``e_``, ``k_``, ``d_``, ``c_``, ``b_``, ``h_``) in ``common/landed_titles``, at any depth,
  its body without the titles nested in it;
* the faiths inside each religion of ``common/religion/religions`` (``... (faiths)``);
* the options of each rule in ``common/game_rules`` (``... (options)``).

``map_data/definition.csv`` is keyed by province id. With a save, the tool also says which removed or changed keys
the save names: its gamestate is scanned once into a set of names, never once per key.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

_TOKEN = re.compile(rb'"(?:[^"\\]|\\.)*"|#[^\n]*|[{}]|[<>!?]?=|[<>]|[^\s{}=<>!?#"]+|[!?]')
_OPERATORS = {b"=", b"<", b">", b"<=", b">=", b"!=", b"?=", b"=="}
_TITLE = re.compile(rb"^[ekdcbh]_[\w\-]+$")
_NAME = re.compile(rb"[A-Za-z_][\w.\-:]*")
SCRIPT_FOLDERS = ("common", "events", "history")
DEFINITION_CSV = "map_data/definition.csv"
LANDED_TITLES = "common/landed_titles"
RELIGIONS = "common/religion/religions"
GAME_RULES = "common/game_rules"

# what the save's use is reported for: kind -> the groups whose keys are of that kind
USE_KINDS = {
    "traits": ("common/traits",),
    "titles": (LANDED_TITLES,),
    "faiths": (f"{RELIGIONS} (faiths)",),
    "religions": (RELIGIONS,),
    "cultures": ("common/culture/cultures",),
    "modifiers": ("common/modifiers", "common/event_modifiers"),
    "buildings": ("common/buildings",),
    "game rules": (GAME_RULES, f"{GAME_RULES} (options)"),
}


def tokens(data: bytes) -> list[bytes]:
    """The script tokens of a file: strings whole, comments and a leading byte-order mark dropped."""
    data = data.removeprefix(b"\xef\xbb\xbf")
    return [t for t in _TOKEN.findall(data) if not t.startswith(b"#")]


def _close(toks: list[bytes], i: int) -> int:
    """Index of the '}' matching the '{' at ``toks[i]`` (the last token when it is never closed)."""
    depth = 0
    for j in range(i, len(toks)):
        if toks[j] == b"{":
            depth += 1
        elif toks[j] == b"}":
            depth -= 1
            if depth == 0:
                return j
    return len(toks) - 1


def entries(toks: list[bytes], start: int = 0, end: int | None = None) -> list[tuple[bytes, int, int]]:
    """``(key, value start, value end)`` for each ``key <op> value`` in ``toks[start:end]``; a value is one token,
    a ``{ ... }`` block, or a word followed by a block (``rgb { ... }``). Bare tokens are skipped."""
    end = len(toks) if end is None else end
    out = []
    i = start
    while i < end:
        t = toks[i]
        if t == b"{":
            i = _close(toks, i) + 1
            continue
        if i + 2 < end and toks[i + 1] in _OPERATORS:
            v = i + 2
            if toks[v] == b"{":
                j = _close(toks, v)
            elif v + 1 < end and toks[v + 1] == b"{":
                j = _close(toks, v + 1)
            else:
                j = v
            out.append((t, v, min(j, end - 1)))
            i = j + 1
            continue
        i += 1
    return out


def _body(toks: list[bytes], v: int, j: int) -> str:
    return " ".join(t.decode("utf-8", "replace") for t in toks[v:j + 1])


def _inner(toks: list[bytes], v: int, j: int) -> tuple[int, int] | None:
    """The token range inside a block value, or None for a plain value."""
    if toks[v] == b"{":
        return v + 1, j
    if v + 1 <= j and toks[v + 1] == b"{":
        return v + 2, j
    return None


def _titles(toks: list[bytes], start: int, end: int, out: dict) -> None:
    """Every landed title in ``toks[start:end]``, at any depth, its body without the titles nested in it."""
    for key, v, j in entries(toks, start, end):
        if not _TITLE.match(key):
            continue
        inner = _inner(toks, v, j)
        if inner is None:
            out.setdefault(key.decode(), []).append(_body(toks, v, j))
            continue
        # the body with the nested titles taken out (each nested title is key, operator, value)
        parts, i = [], inner[0]
        for k2, v2, j2 in entries(toks, *inner):
            if _TITLE.match(k2):
                parts.extend(toks[i:v2 - 2])
                i = j2 + 1
        parts.extend(toks[i:inner[1]])
        out.setdefault(key.decode(), []).append(" ".join(t.decode("utf-8", "replace") for t in parts))
        _titles(toks, inner[0], inner[1], out)


@dataclass
class Definitions:
    """group -> key -> the bodies of its definitions in that group, in file order."""
    groups: dict = field(default_factory=dict)
    files: int = 0

    def add(self, group: str, key: str, body: str) -> None:
        self.groups.setdefault(group, {}).setdefault(key, []).append(body)


def read_definitions(game: Path) -> Definitions:
    """Every definition in a ``game`` folder, grouped by folder."""
    if not game.is_dir():
        raise FileNotFoundError(f"not a folder: {game}")
    d = Definitions()
    for sub in SCRIPT_FOLDERS:
        root = game / sub
        if not root.is_dir():
            continue
        for f in sorted(root.rglob("*.txt"), key=lambda p: p.relative_to(game).as_posix()):
            d.files += 1
            group = f.parent.relative_to(game).as_posix()
            toks = tokens(f.read_bytes())
            if group == LANDED_TITLES or group.startswith(LANDED_TITLES + "/"):
                found: dict = {}
                _titles(toks, 0, len(toks), found)
                for key, bodies in found.items():
                    for b in bodies:
                        d.add(LANDED_TITLES, key, b)
                continue
            for key, v, j in entries(toks):
                if key.startswith(b"@") or key == b"namespace":
                    continue
                name = key.decode("utf-8", "replace")
                d.add(group, name, _body(toks, v, j))
                inner = _inner(toks, v, j)
                if inner is None:
                    continue
                if group == RELIGIONS:
                    for k2, v2, j2 in entries(toks, *inner):
                        if k2 == b"faiths" and _inner(toks, v2, j2):
                            for k3, v3, j3 in entries(toks, *_inner(toks, v2, j2)):
                                d.add(f"{RELIGIONS} (faiths)", k3.decode("utf-8", "replace"), _body(toks, v3, j3))
                elif group == GAME_RULES:
                    for k2, v2, j2 in entries(toks, *inner):
                        if _inner(toks, v2, j2) is not None:
                            d.add(f"{GAME_RULES} (options)", k2.decode("utf-8", "replace"), _body(toks, v2, j2))
    csv = game / DEFINITION_CSV
    if csv.is_file():
        d.files += 1
        for line in csv.read_bytes().removeprefix(b"\xef\xbb\xbf").decode("utf-8", "replace").splitlines():
            line = line.split("#", 1)[0].strip()
            first, _, rest = line.partition(";")
            if first.strip().isdigit():
                d.add(DEFINITION_CSV, first.strip(), ";".join(p.strip() for p in rest.split(";")).rstrip(";"))
    return d


@dataclass
class GroupDiff:
    added: list[str]
    removed: list[str]
    changed: list[str]

    def as_dict(self) -> dict:
        return {"added": self.added, "removed": self.removed, "changed": self.changed}


def _key_order(k: str):
    return (0, int(k), "") if k.isdigit() else (1, 0, k)


def compare(old: Definitions, new: Definitions) -> dict[str, GroupDiff]:
    """group -> what was added, removed and changed; groups with no difference are left out."""
    out = {}
    for group in sorted(set(old.groups) | set(new.groups)):
        a, b = old.groups.get(group, {}), new.groups.get(group, {})
        diff = GroupDiff(sorted(set(b) - set(a), key=_key_order), sorted(set(a) - set(b), key=_key_order),
                         sorted((k for k in set(a) & set(b) if a[k] != b[k]), key=_key_order))
        if diff.added or diff.removed or diff.changed:
            out[group] = diff
    return out


def save_names(gamestate: bytes) -> set[str]:
    """Every name the gamestate contains, found in one pass (quoted or not)."""
    return {m.group().decode("utf-8", "replace") for m in _NAME.finditer(gamestate)}


def used_by_save(diffs: dict[str, GroupDiff], names: set[str]) -> dict[str, dict[str, list[str]]]:
    """kind -> {"removed": [...], "changed": [...]}: the removed or changed keys of that kind the save names."""
    out = {}
    for kind, groups in USE_KINDS.items():
        removed = sorted({k for g in groups if g in diffs for k in diffs[g].removed if k in names}, key=_key_order)
        changed = sorted({k for g in groups if g in diffs for k in diffs[g].changed if k in names}, key=_key_order)
        if removed or changed:
            out[kind] = {"removed": removed, "changed": changed}
    return out
