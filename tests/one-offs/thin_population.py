"""thin_population: a DIAGNOSTIC, not a migration rule. Write a copy of a save with fewer characters, to test whether
a performance problem scales with the number of characters.

Usage:
  python -I tests/one-offs/thin_population.py <in.ck3> <out.ck3> --mode {prunable,dead,living-half} [--seed N]

Modes:
  prunable     remove every characters/dead_prunable entry.
  dead         that, and every dead_unprunable character no living character, title, house or dynasty mentions.
  living-half  remove half (by --seed) of the living characters that hold no title, head no house or dynasty, are
               not the player or the player's family, and are no one's spouse, betrothed, concubine, liege, host,
               employer or imprisoner.

Every reference to a removed character goes with it: an opinion, relation or AI-strategy record about them is deleted
whole, their character_lookup line goes, and every other reference the id schema (idschema.FIELDS) knows is dropped
by translate.rewrite_entry (a list item, a key=value line, or the list item / block of a typed reference). In the
"dead" and "living-half" modes, a character mentioned anywhere else (a section whose references this tool does
not clean) is kept, and counted. The output is checked with the lint and the counts are printed.

Built for a 230 MB gamestate: every section is scanned once for number tokens, matched against a set of ids; an
entry is parsed only when it mentions a removed id; all edits are applied in one gamestate.EditPass. Never writes
in place, and never over an existing file.
"""

from __future__ import annotations

import argparse
import random
import re
import sys
from bisect import bisect_right
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator import idschema as S  # noqa: E402
from ck3_save_migrator import savefile as sf  # noqa: E402
from ck3_save_migrator import translate as T  # noqa: E402
from ck3_save_migrator.lint import SectionIndex, lint_gamestate  # noqa: E402

RULE = "thin-population"
CHAR_SECTIONS = ("living", "dead_unprunable", "characters/dead_prunable")
# top-level sections whose references to a removed character this tool removes with it, in the "dead" and
# "living-half" modes; a mention anywhere else keeps the character
CLEANED = {"living", "dead_unprunable", "characters", "opinions", "relations", "character_memory_manager", "ai",
           "character_lookup"}
# records about a pair or about one character: deleted whole when a party is removed
WHOLE = {"opinions/active_opinions": (b"owner", b"target"), "relations/active_relations": (b"first", b"second")}
_NUMBER = re.compile(rb"(?<![\w.:\-])(\d+)(?![\w.:\-])")
_ENTRY = re.compile(rb"(?m)^(\d+)=\{")
_BLOCKING = re.compile(rb"[\n\t ](spouse|primary_spouse|betrothed|concubine|concubinist|liege|host|employer|"
                       rb"imprisoner)=(\d+)")
_HOUSE = re.compile(rb"\n\tdynasty_house=(\d+)")
_CHILDREN = re.compile(rb"[\n\t ]child=\{([^}]*)\}")
_LOOKUP = re.compile(rb"(?m)^[ \t]*[^\s={}]+=(\d+)[ \t]*$")


class _Traits(dict):
    """Identity trait positions (nothing is translated, only dropped)."""

    def __missing__(self, key):
        return key


def identity_translator() -> T.Translator:
    return T.Translator({sp: T.SpaceMap(sp, identity=True) for sp in S.SPACES}, _Traits(), [])


@dataclass
class Report:
    mode: str
    removed: Counter = field(default_factory=Counter)          # section -> characters removed
    kept: Counter = field(default_factory=Counter)             # why -> candidates kept
    deleted_records: Counter = field(default_factory=Counter)  # kind -> whole records deleted
    references: Counter = field(default_factory=Counter)       # (kind, path) -> references dropped
    lint_errors: int | None = None
    leftovers: Counter = field(default_factory=Counter)        # section -> possible mentions left (number tokens)

    def lines(self) -> list[str]:
        out = [f"mode {self.mode}: {sum(self.removed.values()):,} characters removed"]
        out += [f"  removed from {sec}: {n:,}" for sec, n in sorted(self.removed.items())]
        out += [f"  kept ({why}): {n:,}" for why, n in sorted(self.kept.items())]
        out += [f"  records deleted whole, {kind}: {n:,}" for kind, n in sorted(self.deleted_records.items())]
        out.append(f"  references dropped: {sum(self.references.values()):,}")
        out += [f"    {kind} {path}: {n:,}" for (kind, path), n in sorted(self.references.items())]
        if self.leftovers:
            out.append("  numbers equal to a removed id still in the output (by section; may be other numbers):")
            out += [f"    {sec}: {n:,}" for sec, n in sorted(self.leftovers.items())]
        if self.lint_errors is not None:
            out.append(f"  lint: {self.lint_errors} error(s)")
        return out


# --------------------------------------------------------------------------- reading the save once
class Scan:
    """The gamestate's sections, its character ids by section, and where each candidate id is mentioned."""

    def __init__(self, g: bytes):
        self.g = g
        self.idx = SectionIndex(g)
        self.ids: dict[str, list[bytes]] = {}
        self.entry_starts: dict[str, list[int]] = {}
        for sec in CHAR_SECTIONS:
            b = self.idx.block(sec)
            ms = list(_ENTRY.finditer(g, b.open, b.close)) if b is not None else []
            self.ids[sec] = [m.group(1) for m in ms]
            self.entry_starts[sec] = [m.start() for m in ms]
        self.tops = sorted((b.open, b.close, name) for name, b in self.idx.top.items())
        self._top_starts = [t[0] for t in self.tops]

    def top_at(self, pos: int) -> str | None:
        i = bisect_right(self._top_starts, pos) - 1
        if i >= 0 and self.tops[i][0] <= pos <= self.tops[i][1]:
            return self.tops[i][2]
        return None

    def mentions(self, candidates: set[bytes]) -> dict[bytes, set[str]]:
        """candidate -> the top-level sections that mention it (one pass of the gamestate). A character's own entry
        counts under its section, which is always one this tool cleans, so it never keeps anyone."""
        out: dict[bytes, set[str]] = {}
        for m in _NUMBER.finditer(self.g):
            v = m.group(1)
            if v not in candidates:
                continue
            top = self.top_at(m.start())
            if top is not None:
                out.setdefault(v, set()).add(top)
        return out


# --------------------------------------------------------------------------- choosing who goes
def choose(scan: Scan, mode: str, seed: int, rep: Report) -> set[bytes]:
    g = scan.g
    prunable = set(scan.ids["characters/dead_prunable"])
    if mode == "prunable":
        return prunable
    if mode == "dead":
        cands = set(scan.ids["dead_unprunable"]) - set(scan.ids["living"])
        where = scan.mentions(cands)
        keep_from = {"living": "a living character mentions them", "landed_titles": "a title mentions them",
                     "dynasties": "a house or dynasty mentions them"}
        out = set(prunable)
        for c in cands:
            secs = where.get(c, set())
            why = next((keep_from[s] for s in keep_from if s in secs), None) or \
                next((f"mentioned in {s}" for s in sorted(secs) if s not in CLEANED), None)
            if why:
                rep.kept[why] += 1
            else:
                out.add(c)
        return out
    if mode != "living-half":
        raise ValueError(f"unknown mode {mode!r}")
    living = scan.ids["living"]
    blocked: dict[bytes, str] = {}
    for sec in CHAR_SECTIONS:
        b = scan.idx.block(sec)
        if b is None:
            continue
        for m in _BLOCKING.finditer(g, b.open, b.close):
            blocked.setdefault(m.group(2), f"someone's {m.group(1).decode()}")
    players = set()
    for sec in ("played_character", "currently_played_characters"):
        b = scan.idx.block(sec)
        if b is not None:
            players |= {m.group(1) for m in _NUMBER.finditer(g, b.open, b.close)}
    living_set = set(living)
    players &= living_set
    lb = scan.idx.block("living")
    starts = scan.entry_starts["living"]

    def entry_span(i: int) -> tuple[int, int]:
        return starts[i], (starts[i + 1] if i + 1 < len(starts) else lb.close)

    pos = {cid: i for i, cid in enumerate(living)}
    house_of = {}
    for i, cid in enumerate(living):
        s, e = entry_span(i)
        h = _HOUSE.search(g, s, e)
        if h:
            house_of[cid] = h.group(1)
    player_houses = {house_of[p] for p in players if p in house_of}
    for p in players:
        blocked[p] = "the player"
        s, e = entry_span(pos[p])
        for m in _NUMBER.finditer(g, s, e):                     # the player's spouses, children, father...
            if m.group(1) in living_set and m.group(1) != p:
                blocked.setdefault(m.group(1), "the player's family")
    for i, cid in enumerate(living):
        if house_of.get(cid) in player_houses:
            blocked.setdefault(cid, "the player's family")
        s, e = entry_span(i)
        for m in _CHILDREN.finditer(g, s, e):                   # the player's parents
            if players & set(m.group(1).split()):
                blocked.setdefault(cid, "the player's family")
    free = [c for c in living if c not in blocked]
    where = scan.mentions(set(free))
    eligible = []
    for c in free:
        secs = where.get(c, set())
        why = ("holds or held a title" if "landed_titles" in secs else
               "a house or dynasty mentions them" if "dynasties" in secs else
               next((f"mentioned in {s}" for s in sorted(secs) if s not in CLEANED), None))
        if why:
            rep.kept[why] += 1
        else:
            eligible.append(c)
    for cid, why in blocked.items():
        if cid in living_set:                                   # (the blocking scan also sees the dead's fields)
            rep.kept[why] += 1
    eligible.sort(key=int)
    return set(random.Random(seed).sample(eligible, len(eligible) // 2))


# --------------------------------------------------------------------------- removing them and their references
def _kind_blocks(scan: Scan) -> list[tuple[str, gs.Block]]:
    out = []
    for kind in S.FIELDS:
        if kind == "character":
            continue
        if "/" in kind or kind in scan.idx.top:
            b = scan.idx.block(kind)
            if b is not None:
                out.append((kind, b))
        else:
            out += [(kind, b) for b in gs.find_sections(scan.g, kind)]
    return out


def thin(g: bytes, removed: set[bytes], rep: Report, scan: Scan) -> gs.EditPass:
    ep = gs.EditPass()
    tr = identity_translator()
    rid = {int(x) for x in removed}
    rr = T.RewriteReport()
    counted: set[tuple[str, bytes]] = set()      # 1.20 writes some dead_unprunable entries twice: count once

    def keep(space, value, path):
        return not (space == "character" and value in rid)

    for kind, blk in _kind_blocks(scan):
        hits = [m.start() for m in _NUMBER.finditer(g, blk.open, blk.close) if m.group(1) in removed]
        if not hits:
            continue
        entries = list(gs.iter_entries(g, *blk.body))
        starts = [e.start for e in entries]
        touched = set()
        for h in hits:                                   # the entry each mention is in (none: a section-level scalar)
            i = bisect_right(starts, h) - 1
            if i >= 0 and entries[i].start <= h <= entries[i].close:
                touched.add(i)
        for i in sorted(touched):
            e = entries[i]
            if kind in CHAR_SECTIONS and e.key in removed:
                ep.delete_block(g, e, RULE, f"remove {kind} {e.key.decode()}")
                if (kind, e.key) not in counted:
                    counted.add((kind, e.key))
                    rep.removed[kind] += 1
                continue
            if kind == "ai/ai_strategies" and e.key in removed:
                ep.delete_block(g, e, RULE, "ai strategy of a removed character")
                rep.deleted_records[kind] += 1
                continue
            if kind in WHOLE:
                parties = {c.key: g[c.value_start:c.value_end] for c in gs.iter_children(g, *e.body)
                           if c.key in WHOLE[kind] and c.block is None}
                if any(v in removed for v in parties.values()):
                    ep.delete_block(g, e, RULE, f"{kind} record of a removed character")
                    rep.deleted_records[kind] += 1
                    continue
            new = T.rewrite_entry(g, e, kind, tr, rr, keep=keep)
            if new != g[e.start:e.end]:
                ep.add(gs.Edit(e.start, e.end, new, RULE, f"{kind} references"))
    rep.references.update(rr.dropped)
    lb = scan.idx.block("character_lookup")
    if lb is not None:
        for m in _LOOKUP.finditer(g, lb.open + 1, lb.close):
            if m.group(1) in removed:
                s, e = gs.removal_span(g, m.start(), m.end())
                ep.add(gs.Edit(s, e, b"", RULE, "character_lookup line"))
                rep.deleted_records["character_lookup"] += 1
    return ep


def leftovers(g: bytes, removed: set[bytes]) -> Counter:
    idx = SectionIndex(g)
    tops = sorted((b.open, b.close, name) for name, b in idx.top.items())
    starts = [t[0] for t in tops]
    out: Counter = Counter()
    for m in _NUMBER.finditer(g):
        if m.group(1) in removed:
            i = bisect_right(starts, m.start()) - 1
            out[tops[i][2] if i >= 0 and m.start() <= tops[i][1] else "(top level)"] += 1
    return out


def run(src: Path, out: Path, mode: str, seed: int = 0, say=print) -> Report:
    if out.exists():
        raise sf.OutputExistsError(f"output already exists: {out}")
    save = sf.read_save(src)
    g = save.gamestate
    rep = Report(mode)
    scan = Scan(g)
    removed = choose(scan, mode, seed, rep)
    ep = thin(g, removed, rep, scan)
    ep.apply_to(save)
    rep.leftovers = leftovers(save.gamestate, removed)
    rep.lint_errors = lint_gamestate(save.gamestate, keys=False).errors
    sf.write_save(save, out)
    for line in rep.lines():
        say(line)
    return rep


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("save", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--mode", required=True, choices=("prunable", "dead", "living-half"))
    ap.add_argument("--seed", type=int, default=0, help="which half of the eligible living go (default 0)")
    a = ap.parse_args(argv)
    rep = run(a.save, a.out, a.mode, a.seed)
    return 0 if not rep.lint_errors else 4


if __name__ == "__main__":
    sys.exit(main())
