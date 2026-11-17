"""The game's own rules for a faith's doctrines and tenets, read from its files, each with the file and line to cite.

In 1.20 (By God Alone) a doctrine is a top-level block in common/religion/doctrine_types/ naming its group
(`doctrine_group_type = doctrine_pilgrimage`) and its place in it (`index`; the game fills a group a faith has no
doctrine in with index 0 on load). A tenet is a top-level block in common/religion/tenet_types/; tenets have no group,
a faith holds FAITH_CORE_TENETS_CAP of them (common/defines/00_defines.txt), a tenet's `can_pick` may close it to a
religion (`NOT = { religion = religion:christianity_religion }`) and may require a `unique_*_trigger`, a scripted
trigger listing tenets of which a faith may hold only one (common/scripted_triggers/00_religious_triggers.txt).
Design: 2026-11-16__15-00-12__dev-workflow-process__three-faith-edits-eminent-sites-doctrines-set-faith.md
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

_HEAD = re.compile(r"(?m)^(\w+)\s*=\s*\{")
OPTIONAL_CATEGORIES = {"special", "not_creatable"}   # doctrine_category_types/00_doctrine_category_types.txt:18,23


@dataclass
class Doctrine:
    key: str
    group: str
    index: int | None
    where: str                  # file:line of its definition


@dataclass
class Tenet:
    key: str
    where: str
    closed_to: set = field(default_factory=set)     # religion tags its can_pick excludes
    unique: list = field(default_factory=list)      # names of the unique_*_trigger it requires


@dataclass
class Rules:
    doctrines: dict             # key -> Doctrine
    tenets: dict                # key -> Tenet
    unique_sets: dict           # trigger name -> (set of tenet keys, file:line)
    tenets_cap: int
    cap_where: str
    group_category: dict        # doctrine group -> its category (doctrine_group_types); groups in the `special` and
    #                             `not_creatable` categories may be empty, the others hold one doctrine
    religion_defaults: dict     # religion tag -> {doctrine key: file:line}: the religion's DEFAULT doctrines, written
    #                             in its religion_types entry; a faith of it may choose otherwise (Christianity's
    #                             default pilgrimage is doctrine_pilgrimage_encouraged), so these are not locks

    def group_must_be_filled(self, group: str) -> bool:
        return self.group_category.get(group, "special") not in OPTIONAL_CATEGORIES

    def group_members(self, group: str) -> list:
        return sorted((d for d in self.doctrines.values() if d.group == group),
                      key=lambda d: (d.index if d.index is not None else 99, d.key))


def _blocks(path: Path):
    """(key, body text, line) for every top-level block of a script file."""
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    heads = [(m.start(), m.group(1)) for m in _HEAD.finditer(text)]
    for i, (pos, key) in enumerate(heads):
        end = heads[i + 1][0] if i + 1 < len(heads) else len(text)
        yield key, text[pos:end], text.count("\n", 0, pos) + 1


def _can_pick(body: str) -> str:
    m = re.search(r"(?m)^\tcan_pick\s*=\s*\{", body)
    if not m:
        return ""
    depth, i = 0, m.end() - 1
    for j in range(i, len(body)):
        depth += {"{": 1, "}": -1}.get(body[j], 0)
        if depth == 0:
            return body[i:j + 1]
    return body[i:]


@lru_cache(maxsize=4)
def load(game_dir: str) -> Rules:
    game = Path(game_dir)
    rel = game / "common" / "religion"
    doctrines, tenets, unique_sets, religion_defaults = {}, {}, {}, {}
    for f in sorted((rel / "doctrine_types").glob("*.txt")):
        for key, body, line in _blocks(f):
            g = re.search(r"(?m)^\s*doctrine_group_type\s*=\s*(\w+)", body)
            if g:
                ix = re.search(r"(?m)^\s*index\s*=\s*(\d+)", body)
                doctrines[key] = Doctrine(key, g.group(1), int(ix.group(1)) if ix else None, f"{f.name}:{line}")
    for f in sorted((rel / "tenet_types").glob("*.txt")):
        for key, body, line in _blocks(f):
            if not key.startswith("tenet_"):
                continue
            cp = _can_pick(body)
            closed = set(re.findall(r"NOT\s*=\s*\{\s*religion\s*=\s*religion:(\w+)\s*\}", cp))
            unique = re.findall(r"(unique_\w+_trigger)\s*=\s*yes", cp)
            tenets[key] = Tenet(key, f"{f.name}:{line}", closed, unique)
    for f in sorted((game / "common" / "scripted_triggers").glob("*.txt")):
        for key, body, line in _blocks(f):
            if key.startswith("unique_") and key.endswith("_trigger"):
                members = set(re.findall(r"tenet:(\w+)", body))
                if members:
                    unique_sets[key] = (members, f"{f.name}:{line}")
    for f in sorted((rel / "religion_types").glob("*.txt")):
        text = f.read_text(encoding="utf-8-sig", errors="replace")
        for key, body, line in _blocks(f):
            # the religion's own doctrines: depth-1 `doctrine = x` lines, before its faiths block
            head = body.split("\tfaiths", 1)[0]
            for m in re.finditer(r"(?m)^\tdoctrine\s*=\s*(\w+)", head):
                religion_defaults.setdefault(key, {})[m.group(1)] = \
                    f"{f.name}:{line + head.count(chr(10), 0, m.start())}"
    group_category = {}
    for f in sorted((rel / "doctrine_group_types").glob("*.txt")):
        for key, body, line in _blocks(f):
            c = re.search(r"(?m)^\s*category\s*=\s*(\w+)", body)
            if c:
                group_category[key] = c.group(1)
    cap, cap_where = 3, "game/common/defines/00_defines.txt"
    defines = game / "common" / "defines" / "00_defines.txt"
    if defines.exists():
        text = defines.read_text(encoding="utf-8-sig", errors="replace")
        m = re.search(r"(?m)^\s*FAITH_CORE_TENETS_CAP\s*=\s*(\d+)", text)
        if m:
            cap, cap_where = int(m.group(1)), f"00_defines.txt:{text.count(chr(10), 0, m.start()) + 1}"
    return Rules(doctrines, tenets, unique_sets, cap, cap_where, group_category, religion_defaults)
