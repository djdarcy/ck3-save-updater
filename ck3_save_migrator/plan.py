"""The update plan: what ``ck3update update`` will do to a save, worked out before anything runs.

``plan_update`` is the one source of what happens: ``status`` prints the plan, ``update --dry-run`` runs it in memory
and adds each patch's counts, and ``update`` executes it (the rules it runs are the plan's, in the plan's order). It
is built from the save's metadata and the game folder only; the gamestate is never parsed. The one read of the
gamestate is bounded: its first megabyte, for ``random_seed`` (see ``read_light``).

What the plan holds: the save (versions, date, mods), the game (the install used and the others found), the gap
between them and whether a selected pack covers it, every pack considered and why it is or is not selected (by its
``[applies]`` span), every patch with whether it will run and why, the reference save (given, found, or none, and
which rules skip without one), and the output. A fact that is not knowable before running (how many edits a patch
makes) is None, with a note, never guessed.

The reference pick never chooses a save that descends from the one being updated, nor one this tool wrote (the
director, 2026-10-30). Measured on real saves: the gamestate's ``random_seed`` is carried by this tool's migration
and kept by the game through play, so a candidate with the save's own seed descends from it; this tool's outputs
also have a ``.report.json`` (or ``.lint.json``) beside them. Among the rest, a save whose mods name a
``zz_ref_<date>`` bookmark mod (what ``reference-mod`` writes) is preferred; when two candidates cannot be told
apart, the plan refuses and names them.
"""

from __future__ import annotations

import os
import re
import time
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import savefile as sf
from ._vendor import colors as C
from .config import disabled_ids
from .config import transplant_mode
from .discover import GameInstall, compare_versions, discover_games, parse_version, save_games_dir, save_versions
from .patches import PatchError, read_pack, rules_from_pack
from .patches.model import span_matches
from .patches.pack import run_verdict
from .patches.run import patch_vars
from .rules import REGISTRY, select
from .userpacks import _with_pack_vars, ensure_packs_dir, find_user_packs

FIRST_MB = 1 << 20
_SEED = re.compile(rb"(?m)^random_seed=(\d+)")
_DATE = re.compile(rb"(?m)^\s*meta_date=\"?(-?\d+\.\d+\.\d+)\"?")
_MOD = re.compile(rb'"(mod/[^"]+\.mod)"')

# The built-in rules that do nothing without a reference save, and the one that needs the old game folder. Each
# says so itself when it runs (its "skipped" note); the plan says so beforehand. A test checks the two agree.
NEEDS_REFERENCE = ("R8", "R10", "R9", "R12", "R14", "R16", "R17")
NEEDS_OLD_GAME = ("R15",)
NOT_KNOWABLE = "not knowable before running (update --dry-run runs the patches in memory and counts)"
REFERENCE_STEPS = (
    "ck3update reference-mod --save \"{save}\" --out \"<the game's mod folder>\"",
    "enable the mod it writes in the game's launcher",
    "start a new game from its bookmark, and save as soon as it loads, before you unpause",
    "run this update again (the new save is found in the save folder; or give it with --reference)",
    "docs/reference-save.md explains each step",
)


# --------------------------------------------------------------------------- the bounded read
@dataclass
class Light:
    meta: bytes
    random_seed: str | None
    gamestate_bytes_read: int          # how much of the gamestate was read (at most FIRST_MB)


def read_light(path: Path) -> Light:
    """A save's metadata block, and ``random_seed`` from the first megabyte of its gamestate: a streaming inflate
    of the zip member (a normal save), or the text after the header (a kind-00 text save). Nothing else is read."""
    with open(path, "rb") as f:
        head = f.read(64)
        header = sf.parse_header(head)
        f.seek(len(header.raw))
        if header.kind == sf.KIND_TEXT:
            text = f.read(FIRST_MB)
            meta = text[:sf.meta_block_end(text)]
            chunk, n = text, len(text)
        else:
            meta = f.read(header.meta_len)
            f.seek(0)
            try:
                with zipfile.ZipFile(f) as z, z.open(sf.GAMESTATE) as g:
                    chunk = g.read(FIRST_MB)
            except (zipfile.BadZipFile, KeyError) as exc:
                raise sf.SaveFormatError(f"{path}: the save's zip has no readable gamestate ({exc})") from None
            n = len(chunk)
    m = _SEED.search(chunk)
    return Light(meta, m.group(1).decode() if m else None, n)


def meta_date(meta: bytes) -> str | None:
    m = _DATE.search(meta)
    return m.group(1).decode() if m else None


# --------------------------------------------------------------------------- the plan
@dataclass
class PackChoice:
    id: str
    kind: str                  # "built in", "yours" or "--pack"
    folder: str
    selected: bool
    why: str
    trust: str = ""            # your packs: runs / not trusted / changed since trusted / turned off


@dataclass
class Step:
    id: str
    name: str
    pack: str
    will_run: bool
    reason: str
    matched: int | None = None
    edited: int | None = None
    note: str = NOT_KNOWABLE


@dataclass
class Reference:
    path: str | None
    how: str                   # "given", "$CK3_REFERENCE_SAVE", "found in the save folder", "none"
    why: str
    skips: list[str] = field(default_factory=list)
    candidates: list[str] = field(default_factory=list)
    ambiguous: list[str] = field(default_factory=list)      # refused: the saves it could not choose between


@dataclass
class UpdatePlan:
    save: str
    save_versions: dict
    save_date: str | None
    save_mods: list[str]
    game: dict | None
    other_games: list[dict]
    gap: tuple
    packs: list[PackChoice]
    steps: list[Step]
    reference: Reference
    output: str | None
    refusals: list[str] = field(default_factory=list)
    uncovered: str | None = None
    already_current: bool = False
    notes: list[str] = field(default_factory=list)
    gamestate_bytes_read: int = 0
    # per refusal (by its text): the fix, and the files it names, shown as their folder once and then the names
    fixes: dict = field(default_factory=dict)
    record: str | None = None          # the record line: "<label>: last updated ..." or why there is none
    inputs: dict = field(default_factory=dict)       # the inputs used: given, else pre-filled from the record
    prefilled: list = field(default_factory=list)    # [input, value]: "--var k=" and its value; "--transplant " ...
    prefilled_from: str | None = None                # the record they came from (its label)
    in_place: bool = False
    faces: list = field(default_factory=list)        # R19's layouts, as (field, value) rows for the FACES block
    detected: str | None = None        # the detectors' line: what they did, or why they did not run
    detect_seconds: float | None = field(default=None, compare=False)       # how long the full read took
    detect_mb: float | None = None     # the size of the gamestate the full read inflated
    # each judged step's seconds, in the order judged (the detectors, and the run patches' done checks)
    detect_timings: dict = field(default_factory=dict, compare=False)
    seed: str | None = None            # the save's random_seed: names its save game (a pack's [applies] campaign)
    cache_note: str | None = field(default=None, compare=False)   # the block-index cache: what it wrote or read
    dna_setup: object = field(default=None, repr=False, compare=False)    # dna.Setup, shared with the run
    rules: list = field(default_factory=list, repr=False, compare=False)    # the Rule of each step that runs
    user_packs: list = field(default_factory=list, repr=False, compare=False)   # userpacks.UserPack, for the report

    def has_changes(self) -> bool:
        return not self.refusals and not self.already_current and any(s.will_run for s in self.steps)

    def running(self) -> list[str]:
        return [s.id for s in self.steps if s.will_run]

    def as_dict(self) -> dict:
        d = asdict(self)
        d.pop("rules", None)
        d.pop("dna_setup", None)
        d.pop("user_packs", None)
        d.pop("detect_seconds", None)
        d.pop("detect_timings", None)
        d.pop("cache_note", None)
        return d

    def verdict_lines(self, paint: "Paint | None" = None, seconds: float | None = None,
                      width: int | None = None, layout: dict | None = None) -> list[str]:
        """The answer first (the wtf tools' shape): READY / ALREADY CURRENT / NOTHING TO DO, and REFUSED when the
        plan refuses -- an already-current save can be refused as well (the reference pick), and both are said.
        ``seconds``: the wall time from the command line to this answer, said after it. A line too long for
        ``width`` wraps under its own text."""
        c = paint or Paint()
        width = width or WIDTH_MAX
        out = []
        for i, (word, kind, text) in enumerate(self._verdicts()):
            segs = [(text, None)] + ([(f"  ({seconds:.1f} s)", "note")] if seconds is not None and i == 0 else [])
            got = wrap_segments(segs, c, width - len(word) - 2)
            out.append(f"{c.verdict(word, kind)}  {got[0]}")
            out += [" " * (len(word) + 2) + g for g in got[1:]]
        return out + ([""] if _layout(layout)[1] else [])

    def _verdicts(self) -> list[tuple[str, str, str]]:
        """Each verdict: its word, its colour, and what it says."""
        out = []
        runs, skips = sum(s.will_run for s in self.steps), sum(not s.will_run for s in self.steps)
        if self.already_current:
            at = (f"the save is on the game's version line ({_line_text(self.gap[1])}); no pack is selected for it; "
                  "nothing to do") if self.gap[0] != self.gap[1] else \
                "the save is at the game's version and no pack is selected for it; nothing to do"
            out.append(("ALREADY CURRENT", "info", at + (" (the re-check's findings are in the notes)"
                                               if any(n.startswith("needed: ") for n in self.notes) else "")))
        elif not self.refusals:
            if runs:
                out.append(("READY", "ok", f"{self.gap[0] or '?'} -> {self.gap[1] or '?'}: {runs} patch(es) run, "
                                           f"{skips} skipped"))
            else:
                out.append(("NOTHING TO DO", "info", "no selected patch runs"))
        if self.refusals:
            out.append(("REFUSED", "bad", f"{len(self.refusals)} reason(s), below; nothing is written"))
        return out

    def lines(self, paint: "Paint | None" = None, width: int | None = None,
              layout: dict | None = None) -> list[str]:
        """The plan as blocks (djdarcy's layout, 2026-11-01): a caps header, field names right-aligned within the
        block, one fact per line, a long value wrapped under its own column. Refusals are not repeated here:
        ``refusal_lines`` prints each once. ``width``: the line width (out_width), default WIDTH_MAX."""
        c = paint or Paint()
        width = width or WIDTH_MAX
        v = self.save_versions
        sp = Path(self.save)
        save_rows = [("file", sp.name, "path"), ("folder", str(sp.parent), "path"),
                     ("version", v["version"] or "?", None),
                     ("format", f"save_game_version {v['save_game_version']}, portraits_version "
                                f"{v['portraits_version']}", "note"),
                     ("date", self.save_date or "?", None), ("mods", f"{len(self.save_mods)} listed", None)]
        if self.seed:
            save_rows.append(("seed", self.seed, "note"))
        blocks = [("SAVE", save_rows), ("GAME", game_rows(self.game))]
        blocks += [("ALSO", game_rows(g, also=True)) for g in self.other_games]
        if self.record:
            blocks.append(("RECORD", [("status", self.record, None)] + self._prefill_rows(None, width)))
        gap = [("versions", f"{self.gap[0] or '?'} -> {self.gap[1] or '?'}", None)]
        if self.gap[0] and self.gap[0] == self.gap[1]:
            gap.append(("note", "none: the save is at the game's version", "note"))
        if self.uncovered:
            gap.append(("covered", f"NOT COVERED: the gap {self.gap[0]} -> {self.gap[1]}: no selected pack "
                                   "declares it covers it", "bad"))
        blocks.append(("GAP", gap))
        r = self.reference
        if r.path:
            ref = [("save", r.path, "path"), ("chosen", f"{r.how}: {r.why}", "note")]
        elif r.how == "not needed":
            ref = [("status", "not needed (no patch that will run needs one)", "note")]
        elif r.how == "refused":
            ref = [("status", "none chosen: " + (f"{len(r.ambiguous)} candidates; " if len(r.ambiguous) > 1 else "")
                    + "see the refusal below", "warn")]
        else:
            ref = [("status", f"none ({r.why})", "warn")]
        if not r.path and r.skips:
            ref.append(("skips", "without one these skip: " + ", ".join(r.skips), "warn"))
            if r.how != "refused":                  # several candidates: the fix is --reference, not making one
                ref += [("to make one" if i == 1 else "", f"{i}. {s.format(save=self.save)}", None)
                        for i, s in enumerate(REFERENCE_STEPS, 1)]
        blocks.append(("REFERENCE", ref))
        packs = []
        for p in self.packs:
            trust = f", {p.trust}" if p.trust else ""
            packs.append((p.id, [("selected" if p.selected else "not selected", "ok" if p.selected else "note"),
                                 (f" ({p.kind}{trust}): ", "note"), (p.why, "note")], None))
        blocks.append(("PACKS", packs))
        blocks.append(("PATCHES", [("", "(in the order they run)", "note")]))
        tail = []
        if self.detected:
            det = [("did", self.detected, "note")]
            if self.detect_mb is not None:
                read = f"the whole gamestate, {self.detect_mb:,.1f} MB" + (
                    f", in {self.detect_seconds:.1f} s" if self.detect_seconds is not None else "")
                det.append(("read", read, "note"))
            if self.detect_timings:
                t = self.detect_timings
                slow = sorted(t, key=lambda k: -round(t[k], 1))[:3]     # ties stay in the order judged
                if self.cache_note:
                    det.append(("cache", self.cache_note, "note"))
                det.append(("judged", f"{len(t)} step(s) in {sum(t.values()):.1f} s; slowest "
                                      + ", ".join(f"{k} {t[k]:.1f} s" for k in slow), "note"))
            tail.append(("DETECTORS", det))
        if self.faces:
            tail.insert(0, ("FACES", [(f, v, "note" if f != "target" else None) for f, v in self.faces]))
        tail.append(("OUTPUT", [("file", self.output, "path") if self.output else ("file", "none", "note")]))
        if self.notes:
            tail.append(("NOTES", [("", f"- {n}", "note") for n in self.notes]))
        head = max(len(h) for h, _ in blocks + tail)
        cols = value_columns(blocks + tail, layout, head)       # one computation: global and flow span both parts
        for i, (h, rows) in enumerate(blocks):                  # a pre-fill too long for its column: value below
            if h == "RECORD":
                blocks[i] = (h, rows[:1] + self._prefill_rows(cols[i], width))
        out = render_blocks(blocks, c, width, head, layout, cols[:len(blocks)])
        out += self._patch_rows(c, width)
        return out + ([""] if _layout(layout)[1] else []) + render_blocks(tail, c, width, head, layout,
                                                                           cols[len(blocks):])

    def _prefill_rows(self, col: int | None, width: int) -> list:
        """RECORD's pre-filled rows: one per input; a list value, or a value too long for the line (``col`` known),
        goes on its own lines under the value column; the record they came from is named once, after them."""
        rows = []
        for given, value in self.prefilled:
            items = value if isinstance(value, list) else [value]
            text = given + (" ".join(str(x) for x in items) if not isinstance(value, list) else str(value))
            if isinstance(value, list) or (col is not None and len(text) > width - col):
                rows.append(("pre-filled", given.rstrip(" ="), "info"))
                rows += [("", str(x), "info") for x in items]
            else:
                rows.append(("pre-filled", text, "info"))
        if rows and self.prefilled_from:
            rows.append(("", f"(from the record of {self.prefilled_from})", "note"))
        return rows

    def _patch_rows(self, c: "Paint", width: int) -> list[str]:
        """The patches table: its own aligned columns; a reason too long for the row goes on the line below it,
        under the name."""
        out = []
        nw = max((len(s.name) for s in self.steps), default=0)
        pw = max((len(s.pack) for s in self.steps), default=0)
        for s in self.steps:
            counts = f"matched {s.matched:,} edited {s.edited:,}" if s.matched is not None else ""
            if s.will_run:
                state, said = ("runs", "ok"), (s.reason if s.reason != "runs" else "")    # a done check's verdict
                why = [(x, "note") for x in (counts, said) if x]
            else:
                state = ("skipped", "note")
                why = [(s.reason, "warn" if s.reason.startswith(ACTION_NEEDED) else "note")]
            row = [(f"{IND}{s.id:4} {s.name:{nw}}  ", None), (f"{state[0]:7}", state[1]), ("  ", None),
                   (f"{s.pack:{pw}}", "note")]
            rlen = sum(len(t) for t, _ in row)
            text = "; ".join(t for t, _ in why)
            if not text:
                out.append(paint_segments(row, c).rstrip())
            elif rlen + 2 + len(text) <= width:
                out.append(paint_segments(row + [("  ", None)] + _joined(why), c))
            else:                                  # the reason on its own line(s), under the name
                out.append(paint_segments(row, c))
                indent = len(IND) + 5
                out += [" " * indent + seg for seg in wrap_segments(_joined(why), c, width - indent)]
        if any(s.will_run and s.matched is None and not s.reason.startswith(("needed:", "done:"))
               for s in self.steps):
            lead = "edit counts: "
            got = wrap_segments([(NOT_KNOWABLE, "note")], c, width - len(IND) - len(lead))
            out.append(IND + c.note(lead) + got[0])
            out += [IND + " " * len(lead) + g for g in got[1:]]
        return out

    def refusal_lines(self, paint: "Paint | None" = None, width: int | None = None,
                      layout: dict | None = None) -> list[str]:
        """Each refusal once: the reason, the files it names (their folder once, then the names), the fix; a long
        line wraps under its own text."""
        c = paint or Paint()
        width = width or WIDTH_MAX
        out = [""] if self.refusals and _layout(layout)[1] else []        # apart from the plan above it
        for x in self.refusals:
            d = self.fixes.get(x, {})
            lead = "REFUSED: "
            got = wrap_segments([(x, None)], c, width - len(lead))
            out.append(c.bad("REFUSED") + ": " + got[0])
            out += [" " * len(lead) + g for g in got[1:]]
            if d.get("names"):
                out += [IND + g for g in wrap_segments([("in " + d["folder"], "note")], c, width - len(IND))]
                out += [IND2 + g for n in d["names"] for g in wrap_segments([(n, "path")], c, width - len(IND2))]
            if d.get("fix"):
                got = wrap_segments([(d["fix"], None)], c, width - len(IND) - 5)
                out.append(f"{IND}{c.info('fix')}: {got[0]}")
                out += [" " * (len(IND) + 5) + g for g in got[1:]]
        return out


IND, IND2 = "  ", "    "     # a section's continuation lines, and the items under them

# skip reasons the player can act on (shown as a warning, not a note)
ACTION_NEEDED = ("needs a reference save", "needs the old game folder", "its pack is not trusted",
                 "its pack is changed since trusted", "needs --var")


class Paint:
    """Colour for the plan's lines: plain unless ``on`` (the caller decides with colors.should_use_color, so
    NO_COLOR, FORCE_COLOR, CK3UPDATE_COLOR and a pipe all apply)."""

    def __init__(self, on: bool = False):
        self.on = on

    def _c(self, text: str, *codes: str) -> str:
        return C.colorize(text, *codes) if self.on else text

    def label(self, t: str) -> str: return self._c(t, C.BOLD)                      # noqa: E704
    def path(self, t: str) -> str: return self._c(t, C.CYAN)                       # noqa: E704
    def ok(self, t: str) -> str: return self._c(t, C.GREEN)                        # noqa: E704
    def warn(self, t: str) -> str: return self._c(t, C.YELLOW)                     # noqa: E704
    def bad(self, t: str) -> str: return self._c(t, C.BOLD, C.BRIGHT_RED)          # noqa: E704
    def info(self, t: str) -> str: return self._c(t, C.BLUE)                       # noqa: E704
    def note(self, t: str) -> str: return self._c(t, C.DIM)                        # noqa: E704

    def verdict(self, t: str, kind: str) -> str:
        code = {"ok": C.GREEN, "info": C.BLUE, "bad": C.BRIGHT_RED}[kind]
        return self._c(t, C.BOLD, code)

    def by(self, t: str, style: str | None) -> str:
        """``t`` in the named style (label, path, ok, warn, bad, info, note); None leaves it plain."""
        return t if style is None or not t else getattr(self, style)(t)


# ---- the block layout (djdarcy, 2026-11-01): one fact per line, never wrapped back under a header
WIDTH_MIN, WIDTH_MAX = 60, 120      # the line width: the terminal's, within these (a pipe gets WIDTH_MAX)
GAP = 2                             # between the header column and the longest field name ([display] gap)


def _layout(layout: dict | None) -> tuple[int, bool]:
    """(gap, blank lines between blocks) from the [display] settings (config.display_settings); defaults when None."""
    layout = layout or {}
    return int(layout.get("gap", GAP)), layout.get("spacing", SPACING) != "compact"


def value_columns(blocks: list, layout: dict | None = None, head: int | None = None) -> list[int]:
    """The column each block's values start at, by [display] align (djdarcy, 2026-11-01). A block's natural column
    is its header, the gap, its longest field name and ": ".

    - "blocks": every header padded to the longest header, then the gap, then the block's own field names (one
      header column for all; each block's colons line up within it).
    - "global": every block at the largest natural column, so every colon in the output lines up.
    - "flow": a block of several rows at its own natural column; a one-row block at its own or the block above's,
      whichever is larger (it never shrinks back under a block that was pushed out)."""
    gap = _layout(layout)[0]
    align = (layout or {}).get("align", ALIGN)
    head = head if head is not None else max((len(h) for h, _ in blocks), default=0)

    def fw(rows):
        return max((len(f) for f, _, _ in rows), default=0)
    natural = [len(h) + gap + (fw(rows) + 2 if fw(rows) else 0) for h, rows in blocks]
    if align == "global":
        return [max(natural, default=0)] * len(blocks)
    if align == "flow":
        out = []
        for (h, rows), n in zip(blocks, natural):
            out.append(n if len(rows) > 1 or not out else max(n, out[-1]))
        return out
    return [head + gap + (fw(rows) + 2 if fw(rows) else 0) for h, rows in blocks]


# the [display] defaults (djdarcy, 2026-11-01; config.DISPLAY holds the same): flow alignment, no blank lines
ALIGN = "flow"                      # [display] align: "flow", "global" or "blocks" (value_columns)
SPACING = "compact"                 # [display] spacing: "compact" or "blank"


def out_width(stream=None) -> int:
    """The width to lay the plan out in: ``COLUMNS`` if set, else the terminal's (one short of its edge, so a
    full line never wraps), else WIDTH_MAX; always within WIDTH_MIN..WIDTH_MAX."""
    w = None
    cols = os.environ.get("COLUMNS", "").strip()
    if cols.isdigit():
        w = int(cols)
    else:
        try:
            if stream is not None and stream.isatty():
                w = os.get_terminal_size(stream.fileno()).columns - 1
        except (AttributeError, ValueError, OSError):
            w = None
    return min(WIDTH_MAX, max(WIDTH_MIN, w or WIDTH_MAX))


def _spans(text: str, avail: int) -> list[tuple[int, int]]:
    """Where ``text`` breaks into lines of at most ``avail`` characters: at a space when there is one, else hard."""
    avail = max(avail, 10)
    spans, i, n = [], 0, len(text)
    while i < n:
        if n - i <= avail:
            spans.append((i, n))
            break
        cut = text.rfind(" ", i, i + avail + 1)
        if cut <= i:
            cut, nxt = i + avail, i + avail
        else:
            nxt = cut + 1
        spans.append((i, cut))
        i = nxt
        while i < n and text[i] == " ":
            i += 1
    return spans or [(0, 0)]


def wrap_segments(segs: list, c: "Paint", avail: int) -> list[str]:
    """``segs`` ((text, style) pairs, read as one string) wrapped to ``avail`` columns, each line painted: the
    colour follows the text across a break."""
    text = "".join(t for t, _ in segs)
    out = []
    for a, b in _spans(text, avail):
        line, at = [], 0
        for t, style in segs:
            lo, hi = max(a, at), min(b, at + len(t))
            if lo < hi:
                line.append(c.by(text[lo:hi], style))
            at += len(t)
        out.append("".join(line))
    return out


def paint_segments(segs: list, c: "Paint") -> str:
    return "".join(c.by(t, style) for t, style in segs)


def _joined(parts: list) -> list:
    """(text, style) parts joined with "; " between them."""
    out = []
    for i, p in enumerate(parts):
        out += ([("; ", None)] if i else []) + [p]
    return out


def game_rows(g: dict | None, also: bool = False) -> list:
    """A game install's block rows: its version, folder, and how it was found."""
    if g is None:
        return [("found", "none (give --game-dir)", "warn")]
    return [("version", g["version"] or "unknown", None), ("path", g["path"], "path"),
            ("found", g["source"] + ("; not used" if also else ""), "note")]


def render_blocks(blocks: list, c: "Paint", width: int, head: int | None = None,
                  layout: dict | None = None, cols: list[int] | None = None) -> list[str]:
    """Blocks of ``(HEADER, rows)``; a row is ``(field, value, style)``, or ``(field, [(text, style), ...], None)``
    for a value in several colours. Each block's values start at its column (``cols``, default value_columns: the
    [display] gap and align); its field names are right-aligned to end just before ": ". A value too long for the
    line wraps under its own column. A field named "" shows no colon. A blank line separates the blocks unless
    [display] spacing is "compact"."""
    blank = _layout(layout)[1]
    cols = cols if cols is not None else value_columns(blocks, layout, head)
    out = []
    for (h, rows), col in zip(blocks, cols):
        if out and blank:
            out.append("")
        fw = max((len(f) for f, _, _ in rows), default=0)
        name_end = col - 2 if fw else col              # where the field names end (their colon follows)
        for i, (f, value, style) in enumerate(rows):
            segs = value if isinstance(value, list) else [(str(value), style)]
            lead = c.label(h) if i == 0 else ""
            room = name_end - (len(h) if i == 0 else 0)
            name = (c.note(f"{f:>{room}}") + (": " if f else "  ")) if fw else " " * room
            bullet = "- " if isinstance(value, str) and value.startswith("- ") else ""    # wraps under its text
            if bullet:
                segs = [(str(value)[2:], style)]
            got = wrap_segments(segs, c, width - col - len(bullet))
            out.append(lead + name + c.by(bullet, style) + got[0])
            out += [" " * (col + len(bullet)) + g for g in got[1:]]
    return out


def _cache_note(event: list) -> str | None:
    """The plan's word on the block-index cache (on by default): where it wrote or read the save's index."""
    if not event:
        return None
    what, path, size = event
    if what == "read":
        return f"read this save's block index from the cache ({path.parent}), not built again"
    return (f"wrote this save's block index to {path.parent} ({size / 1e6:,.0f} MB; the newest 2 kept, a day at "
            "most; `ck3update cache clear` empties it, [cache] index = false turns it off)")


def _game(g: GameInstall | None) -> dict | None:
    return None if g is None else {"source": g.source, "path": str(g.path), "version": g.version}


NOT_SELECTED = "its pack is not selected for this save and game"


def _span_why(applies: dict | None, sv: str | None, gv: str | None,
              seed: str | None = None) -> tuple[bool, str, bool, str]:
    """(selected, why, declares a span that covers this save and game, the reason its patches are skipped when not
    selected). A ``campaign`` in ``[applies]`` selects the pack only for the save game whose random_seed it names."""
    if not applies:
        return True, "no version span declared (matches any version)", False, ""
    parts, ok = [], True
    camp = applies.get("campaign")
    if camp:
        mine = seed is not None and str(seed) == camp["seed"]
        parts.append(f"campaign {camp['name']}: this save's random_seed "
                     + ("is its seed" if mine else f"({seed or 'not found'}) is not its seed ({camp['seed']})"))
        if not mine:
            return False, "; ".join(parts), False, f"for another save game ({camp['name']})"
    spans = {k: v for k, v in applies.items() if k in ("save", "game")}
    for key, ver in (("save", sv), ("game", gv)):
        span = spans.get(key)
        if span is None:
            if spans:
                parts.append(f"{key}: any")
            continue
        m = span_matches(span, ver)
        ok = ok and bool(m)
        parts.append(f"{key} {ver or '?'} {'matches' if m else 'does not match' if m is False else 'cannot be compared to'}"
                     f" {span}")
    return ok, "; ".join(parts), ok and bool(spans), NOT_SELECTED


REWORK = "1.13"                       # the map rework: a save below it needs the new-map rules to load in 1.20
TRANSPLANT = ("R14", "R15", "R16")    # rules.select adds R17, which writes what they plan
CONTEXT_PRESENT = {"target_version", "target_save_game_version", "wos_shape", "expansion_orders", "mod_dirs"}


def _excluded_ids(spec: str) -> set[str]:
    by = {k.lower(): r.id for r in REGISTRY for k in (r.id, r.name)}
    return {by[t.strip()[1:].lower()] for t in spec.split(",") if t.strip().startswith("-")
            and t.strip()[1:].lower() in by}


# built-in rules that belong to the one before them: a user pack placed after R17 (the transplant's write) runs after
# R19 too, which carries the faces of the people R17 wrote, so the faces are done before any user pack
BUILT_IN_FOLLOWERS = {"R17": ("R19",)}


def _faces_rows(st, transplanting: bool) -> list[tuple[str, str]]:
    """The FACES block: the layouts R19 translates between (with their folders and gene counts) and the
    portraits_version it stamps."""
    def lay(x) -> str:
        return f"{x.name}: {x.places} genes, {x.length} characters"
    rows = [("source", lay(st.source)), ("target", lay(st.target)), ("from", st.target_from)]
    if st.reference is not None and transplanting:
        rows.insert(1, ("transplanted", lay(st.reference)))
    rows[1:1] = [("source mod", f"{m}: {origin}") for m, origin in st.source_mods]
    mods = [(label, d) for label, d in st.target.spec if label != "vanilla"]
    rows += [("target mod", f"{label}: {d}") for label, d in mods]
    rows.append(("portraits", f"portraits_version {st.portraits_version if st.portraits_version is not None else '?'}"
                              f" ({st.portraits_why})"))
    return rows


def skipped_needs(need: list[str]) -> str:
    """A step's reason when what it needs is skipped: "needs R14, which is skipped" / "needs R14, R16, which are
    skipped"."""
    return f"needs {', '.join(need)}, which {'is' if len(need) == 1 else 'are'} skipped"


def _line_text(v: str | None) -> str:
    """A version's line as text ("1.20.1.3" -> "1.20")."""
    pv = _line(v)
    return ".".join(str(x) for x in pv) if pv else (v or "?")


def _line(v: str | None):
    pv = parse_version(v)
    return pv[:2] if pv and len(pv) >= 2 else pv


def _named_ids(spec: str) -> set[str]:
    by = {k.lower(): r.id for r in REGISTRY for k in (r.id, r.name)}
    return {by[t.strip().lower()] for t in spec.split(",")
            if t.strip() and t.strip().lower() != "all" and not t.strip().startswith("-") and t.strip().lower() in by}


def plan_update(save: str | Path, *, game_dir: str | None = None, reference: str | None = None,
                old_game_dir: str | None = None, rules_spec: str | None = None, output: str | None = None,
                packs: list[str] | None = None, allow_run: bool = False, save_folder: Path | None = None,
                force: bool = False, create_packs_dir: bool = False, variables: dict | None = None,
                transplant: str | None = None, use_record: bool = True, in_place: bool = False,
                detect: bool = False, progress=None, no_dna: bool = False,
                portrait_mods: list[str] | None = None, old_portrait_mods: list[str] | None = None,
                face_changes: list[str] | None = None) -> UpdatePlan:
    """The plan for updating ``save`` (see the module docstring). Refusals are collected in ``refusals`` (the
    caller exits 1); a bad option (an unknown rule, a broken pack) raises ValueError as ``migrate`` does.

    Every decision is made here, before anything runs: a pack for another save game (its ``campaign``), a gap within
    one major.minor line (assumed compatible), the reference (searched for only when a step that will run needs
    one), a run patch's unmet ``needs`` (skipped, naming the ``--var``), its done check (a run patch already done
    is skipped), a step whose prerequisite is skipped, and the new-map transplant (``transplant="auto"``).
    ``variables``: the caller's ``--var``/``--vars`` (``<patch id>.<name>`` for one patch).

    Making the plan writes nothing: the player's packs folder is only read, unless ``create_packs_dir`` (``update``
    without ``--dry-run`` creates it on its first run, as ``migrate`` does). It reads the whole save only when a
    selected run patch declares a done check (to judge it), or with ``detect`` (the CLI's default): the built-in
    rules' detectors (detect.py) then judge each built-in step needed or done, and a save already on the game's
    version line is re-checked with them (unless its record says this tool version or a later one updated it).
    The whole save is read once for both, and not at all when the plan is already refused (fail early: the
    refusal is the answer, and fixing it comes first).

    ``progress``: called with a short line naming each slow stage as it starts (the CLI's spinner)."""
    stage = progress or (lambda text: None)
    from .patches import blockindex
    blockindex.LAST_EVENT.clear()
    save = Path(save)
    light = read_light(save)
    sv = save_versions(light.meta)
    date = meta_date(light.meta)
    mods = [m.decode("utf-8", "replace") for m in _MOD.findall(light.meta)]
    installs = discover_games(game_dir, os.environ.get("CK3_GAME_DIR"))
    game = installs[0] if installs else None
    gv = game.version if game else None
    refusals: list[str] = []
    notes: list[str] = []
    fixes: dict = {}
    if game is None:
        refusals.append("no game install found")
        fixes["no game install found"] = {"fix": "give --game-dir \"<the game's 'game' folder>\""}
    elif gv is None:
        refusals.append(f"the game's version could not be read (no readable launcher/launcher-settings.json in "
                        f"{game.install}); update chooses its packs by version (migrate still works without it)")
    elif compare_versions(sv["version"], gv) == 1:
        refusals.append(f"the save was written by game version {sv['version']}, newer than the game at {game.path} "
                        f"(version {gv}); update brings a save from an older version to the game's")
    # a given --old-game-dir is checked here, before anything runs: R15 reads its map, and a wrong folder would be
    # read as a map with no titles (the 0.4.0 sweep's lint error, 2026-11-02); a recorded one is checked below
    if old_game_dir and not (Path(old_game_dir) / "common" / "landed_titles").is_dir():
        why = (f"--old-game-dir \"{old_game_dir}\" is not a folder" if not Path(old_game_dir).is_dir() else
               f"--old-game-dir \"{old_game_dir}\" has no common/landed_titles: it is not a game's 'game' folder")
        refusals.append(why)
        fixes[why] = {"fix": "give the 'game' folder of the game version the save was made with (the one holding "
                             "common and gfx)"}

    # a given --old-portrait-mods entry that names no installed mod and no folder is refused, naming it (a recorded
    # one is checked below, and is not used rather than refused)
    if old_portrait_mods is not None:
        from .dna import unresolved
        for x in unresolved(old_portrait_mods, game.path if game else None):
            why = f"--old-portrait-mods \"{x}\" is no installed Workshop mod and no folder"
            refusals.append(why)
            fixes[why] = {"fix": "give the Workshop id of an installed mod, or the folder of the save's own build of "
                                 "the mod (the one holding common/genes)"}

    variables = dict(variables or {})
    seed = light.random_seed

    # ---- the save game's record: what was not given this time takes the newest recorded value
    rec_line, prefilled, rec = None, [], None
    if not use_record:
        rec_line = "not used (--no-record)"
    elif seed is None:
        rec_line = "none: the save's random_seed was not found, so no record is kept for it"
    else:
        from .record import latest_inputs, read_record, summary
        rec = read_record(seed)
        if rec is None:
            rec_line = "none yet (this update starts one)"
        else:
            rec_line = summary(rec)
            label = rec.get("label", "?")
            last = latest_inputs(rec)

            def missing(v) -> bool:
                vals = v if isinstance(v, list) else [v]
                return any(isinstance(x, str) and Path(x).is_absolute() and not Path(x).exists() for x in vals)
            for k, v in (last.get("vars") or {}).items():
                if k in variables:
                    continue
                if missing(v):
                    notes.append(f"the record of {label} has --var {k}={v}, which no longer exists; not used")
                    continue
                variables[k] = v
                prefilled.append([f"--var {k}=", v])
            rod = last.get("old_game_dir")
            if old_game_dir is None and rod:
                if missing(rod):
                    notes.append(f"the record of {label} has --old-game-dir {rod}, which no longer exists; not used")
                else:
                    old_game_dir = rod
                    prefilled.append(["--old-game-dir ", rod])
            ropm = last.get("old_portrait_mods")
            if old_portrait_mods is None and ropm is not None:
                from .dna import unresolved
                gone = unresolved(list(ropm), game.path if game else None)
                if gone:
                    notes.append(f"the record of {label} has --old-portrait-mods {', '.join(gone)}, which no longer "
                                 "exists; not used")
                else:
                    old_portrait_mods = list(ropm)
                    prefilled.append(["--old-portrait-mods ", ",".join(ropm) if ropm else "''"])
            if transplant is None and last.get("transplant") is not None:
                prefilled.append(["--transplant ", last["transplant"]])
                transplant = last["transplant"]
            if last.get("portraits_version") is not None:
                notes.append("the record's portraits_version is no longer used; R19 sets it from the target")
    # --wos-shape shapes the outputs, not the plan: update pre-fills it from the record itself (cli.cmd_update)
    inputs = {"vars": dict(variables), "old_game_dir": old_game_dir, "transplant": transplant,
              "old_portrait_mods": old_portrait_mods, "face_changes": face_changes}

    # ---- the new-map transplant: R14-R16 (and R17) by need, when the switch is on
    mode = transplant or transplant_mode()
    crosses = bool(sv["version"] and gv and compare_versions(sv["version"], REWORK) == -1
                   and compare_versions(gv, REWORK) != -1)
    spec = rules_spec if rules_spec is not None else "all"
    off, named = set(disabled_ids()), _named_ids(spec)
    if mode == "auto" and crosses:
        add = [r for r in TRANSPLANT if r not in _excluded_ids(spec) and r not in named]
        if add:
            spec = spec + "," + ",".join(add)
    chosen = {r.id for r in select(spec)}                         # raises ValueError on a bad --rules
    if crosses and mode != "auto" and not set(TRANSPLANT) & chosen:
        notes.append("this save crosses the 1.13-1.20 map rework: it loads only with the transplant "
                     "(--rules all,R14,R15,R16, or --transplant auto)")

    # ---- the built-in pack, and the rules --rules selects from it
    shipped = read_pack()
    ok, why, covers, skip_why = _span_why(shipped.applies, sv["version"], gv, seed)
    pack_rows = [PackChoice(shipped.id, "built in", "(inside the package)", ok, why)]
    covered = covers
    steps: list[Step] = []
    rules: dict[str, object] = {}
    # per step: needs a reference; the patch (for needs and done checks); whether its code may run; its vars.toml;
    # the ids it requires
    info: dict[str, dict] = {}
    sl, gl = _line(sv["version"]), _line(gv)
    same_line = bool(sl and gl and sl == gl)
    gspan = (shipped.applies or {}).get("game")
    recheck = bool(not ok and same_line and skip_why == NOT_SELECTED and (gspan is None or span_matches(gspan, gv)))
    # an up-to-date save: every rule --rules does not leave out is a candidate (opt-in ones too, so the transplant
    # is judged, and guarded, rather than silently absent); a --rules that names rules without "all" keeps to them
    plus = [t.strip().lower() for t in spec.split(",") if t.strip() and not t.strip().startswith("-")]
    candidates = (({r.id for r in REGISTRY} - _excluded_ids(spec)) if (not plus or "all" in plus) else set(chosen)) \
        if recheck else set()
    for r in REGISTRY:
        reason, run = "runs", True
        if not ok and (r.id not in candidates or (r.id == "R19" and no_dna)):
            reason, run = skip_why, False
        elif not ok and r.id in chosen and (r.id in named or (r.id == "R17" and set(TRANSPLANT) & named)):
            reason = "runs (named in --rules; the pack's span does not select this save)"
        elif not ok and r.id in off:
            reason, run = "turned off in your config (`ck3update enable` turns it back on)", False
        elif not ok:
            reason, run = RECHECK, False                  # judged below: the record, then its detector
        elif r.id == "R19" and no_dna:
            reason, run = "turned off by --no-dna (the faces stay in the save's own gene layout)", False
        elif r.id not in chosen:
            reason, run = ("opt-in: not in --rules" if not r.default else "not selected by --rules"), False
        elif r.id in off and r.id not in named:
            reason, run = "turned off in your config (`ck3update enable` turns it back on)", False
        elif r.id in NEEDS_OLD_GAME and not old_game_dir:
            reason, run = "needs the old game folder (--old-game-dir), and none was given", False
        steps.append(Step(r.id, r.name, shipped.id, run, reason))
        rules[r.id] = r
        info[r.id] = {"needs_ref": r.id in NEEDS_REFERENCE, "patch": None, "requires": tuple(r.requires)}

    def pack_info(p, may_run: bool, pvars: dict) -> dict:
        needs = p.run["needs"] if p.run else ()
        return {"needs_ref": "reference" in needs, "patch": p, "may_run": may_run, "pack_vars": pvars,
                "requires": tuple(p.requires)}

    # ---- your packs, then --pack folders
    if create_packs_dir:
        ensure_packs_dir()
    extra: list[tuple[object, list[Step]]] = []
    found = find_user_packs().packs
    for up in found:
        ok, why, covers, skip_why = _span_why(up.pack.applies, sv["version"], gv, seed)
        pack_rows.append(PackChoice(up.id, "yours", str(up.folder), ok, why, up.state))
        runnable = up.state == "runs" or (allow_run and up.state != "turned off")
        if ok and runnable:
            covered = covered or covers
            built = {r.id: _with_pack_vars(r, up.vars) for r in rules_from_pack(up.pack, allow_run=True)}
        else:
            built = {}
        own = []
        for p in up.pack.ordered():
            if not ok:
                reason = skip_why
            elif up.state in ("not trusted", "changed since trusted") and not allow_run:
                reason = (f"its pack is {up.state}: `ck3update trust {up.id}` lets it run")
            elif not p.default:
                reason = "default = false"
            elif p.id in off:
                reason = "turned off in your config (`ck3update enable` turns it back on)"
            else:
                reason = "runs"
            own.append(Step(p.id, p.name, up.id, reason == "runs", reason))
            info[p.id] = pack_info(p, runnable, up.vars)
            if p.id in built:
                rules[p.id] = built[p.id]
        extra.append((up.pack, own))
    named_packs = set()               # packs given with --pack: a missing need of theirs refuses (below)
    for folder in packs or []:
        pk = read_pack(folder)
        ok, why, covers, skip_why = _span_why(pk.applies, sv["version"], gv, seed)
        pack_rows.append(PackChoice(pk.id, "--pack", str(folder), ok, why))
        named_packs.add(pk.id)
        if not ok:
            # named, but not for this save: the run goes on without it, said where the plan's notes are read
            notes.append(f"--pack {pk.id} does not apply to this save ({why}); its patches do not run")
        built = {r.id: r for r in rules_from_pack(folder, allow_run=allow_run)} if ok else {}   # refuses code
        covered = covered or (ok and covers)
        own = []
        for p in pk.ordered():
            reason = (skip_why if not ok else "default = false" if not p.default else "runs")
            own.append(Step(p.id, p.name, pk.id, reason == "runs", reason))
            info[p.id] = pack_info(p, allow_run, {})
            if p.id in built:
                rules[p.id] = built[p.id]
        extra.append((pk, own))

    # ---- order: a pack with `after` runs right after that patch; the others after everything before them
    for pk, own in extra:
        if pk.after is None:
            steps += own
            continue
        at = next((i for i, s in enumerate(steps) if s.id == pk.after), None)
        if at is None:
            refusals.append(f"pack {pk.id}: after = {pk.after!r} names no patch of the packs before it")
            steps += own
            continue
        while at + 1 < len(steps) and steps[at + 1].id in BUILT_IN_FOLLOWERS.get(pk.after, ()):
            at += 1                                    # R19 finishes what R17 wrote: a pack after R17 follows both
        while at + 1 < len(steps) and getattr(steps[at + 1], "_after", None) == pk.after:
            at += 1                                    # several packs after one patch: in loading order
        for s in own:
            s._after = pk.after
        steps[at + 1:at + 1] = own

    # ---- the reference: searched for only when a step that will run needs one (given or named, it is used)
    given_ref = reference not in (None, "") or os.environ.get("CK3_REFERENCE_SAVE") not in (None, "")
    if given_ref or any(s.will_run and info[s.id]["needs_ref"] for s in steps):
        ref = _reference(reference, save, sv, date, seed, gv, save_folder)
    else:
        ref = Reference(None, "not needed", "no patch that will run needs one")
    if ref.how == "refused":
        refusals.append(ref.why)
        amb = [Path(x) for x in ref.ambiguous]
        fixes[ref.why] = {"fix": "pick one with --reference \"<one of these>\"",
                          "folder": str(amb[0].parent) if amb else None, "names": [p.name for p in amb]}
    for s in steps:
        if s.will_run and info[s.id]["needs_ref"] and not ref.path:
            s.will_run, s.reason = False, "needs a reference save, and there is none"
    ref.skips = [s.id for s in steps if s.reason.startswith("needs a reference")]
    if crosses and mode == "auto" and not ref.path and set(ref.skips) & set(TRANSPLANT):
        notes.append("this save crosses the 1.13-1.20 map rework: it needs a reference save to load in 1.20 (the "
                     "transplant copies the new regions from one); the steps to make one are above")
    # A reference named by hand for the new-map steps must be on the campaign's date: they copy the new regions'
    # people as the reference has them, and the wrong date brings the wrong generation. The search in the save
    # folder only takes one on the date already; a religion-only reference may be from any date.
    if ref.path and ref.how in ("given", "$CK3_REFERENCE_SAVE") and date and \
            any(s.will_run and s.id in TRANSPLANT for s in steps):
        try:
            rdate = meta_date(read_light(Path(ref.path)).meta)
        except (OSError, sf.SaveFormatError):
            rdate = None
        if rdate and rdate != date:
            why = (f"the reference save is dated {rdate}, the save {date}: the new map's regions would be copied "
                   "from the wrong moment")
            refusals.append(why)
            fixes[why] = {"fix": f"make one on {date} with `ck3update reference-mod --save \"<your save>\"` (README, "
                                 "Quick start), or leave the new-map steps out (--transplant off)"}

    # ---- run patches' needs and variables, known before anything runs
    known_ctx = {"game_dir": str(game.path) if game else None, "reference": ref.path,
                 "old_game_dir": old_game_dir}

    def values_for(sid: str) -> dict:
        i = info[sid]
        return {**{k: v for k, v in known_ctx.items() if v not in (None, "")},
                **i.get("pack_vars", {}), **patch_vars(sid, variables)}

    ids = {s.id for s in steps}
    for k in variables:
        if "." in k and k.split(".", 1)[0] not in ids:
            refusals.append(f"--var {k}: no patch {k.split('.', 1)[0]} in this plan")
    # a bare name applies to every selected patch of one pack that needs it; patches of different packs needing
    # it are refused (one folder or word is meant for one pack's patches), naming them
    for name in sorted(k for k in variables if "." not in k):
        users = [s for s in steps if s.will_run and info[s.id]["patch"] is not None
                 and info[s.id]["patch"].run and name in info[s.id]["patch"].run["needs"]]
        if len({u.pack for u in users}) > 1:
            named_users = ", ".join(f"{u.id} (pack {u.pack})" for u in users)
            x = (f"--var {name} is needed by patches of different packs, {named_users}: say which with "
                 f"--var <patch id>.{name}=...")
            refusals.append(x)
            fixes[x] = {"fix": " ".join(f"--var {u.id}.{name}=..." for u in users)}
    for s in steps:
        p = info[s.id]["patch"]
        if not s.will_run or p is None or not p.run:
            continue
        have = values_for(s.id)
        for name, help_text in p.run["needs_help"].items():
            if name == "reference" or name in CONTEXT_PRESENT or have.get(name) not in (None, ""):
                continue
            if name == "old_game_dir":
                s.will_run, s.reason = False, "needs the old game folder (--old-game-dir), and none was given"
            else:
                s.will_run = False
                s.reason = f"needs --var {name}" + (f" ({help_text})" if help_text else "")
            if s.pack in named_packs:
                # a pack named on the command line was asked for: writing a save without what it adds would look
                # like success (djdarcy 2026-11-06, the play11 build without --vars: no faces step, one quiet line)
                x = (f"--pack {s.pack}: patch {s.id} cannot run, it {s.reason}")
                refusals.append(x)
                fixes[x] = {"fix": f"give --var {name}=... (or --vars <file> with {name} in it), or leave out "
                                   f"--pack {s.pack}"}
            break

    # ---- the gap: judged on major.minor (a hotfix of the same line is assumed compatible). Known before the full
    # read, so a gap nothing covers refuses before it
    uncovered = None
    if gv and sv["version"] and not same_line and not covered and not refusals:
        uncovered = (f"the gap {sv['version']} -> {gv}: no selected pack declares it covers it (a pack's "
                     "[applies] span); nothing would bring the save to the game's version")
        refusals.append(uncovered)
        fixes[uncovered] = {"fix": "a pack in your packs folder whose [applies] declares this span "
                                   "(docs/writing-a-patch.md), or `ck3update migrate` with the rules you choose"}
    # fail early (djdarcy, 2026-11-01): a plan already refused does not read the whole save; its refusal is the
    # answer, and status after the fix judges the rest
    refused = bool(refusals)

    # ---- run patches' done checks: one already done does not run (the only full read of the save)
    checks = [s for s in steps if s.will_run and info[s.id]["patch"] is not None and info[s.id]["patch"].run
              and (info[s.id]["patch"].done or info[s.id]["patch"].run.get("done_command"))]
    full: dict = {}
    timings: dict[str, float] = {}

    def gamestate() -> bytes:
        if "g" not in full:
            stage(f"reading the whole save ({save.stat().st_size / 1e6:,.1f} MB compressed)")
            t = time.perf_counter()
            full["g"] = sf.read_save(save).gamestate
            full["seconds"] = time.perf_counter() - t
        return full["g"]
    if checks and not refused:
        for n, s in enumerate(checks, 1):
            i = info[s.id]
            g = gamestate()
            stage(f"checking {s.id} {s.name} ({n} of {len(checks)}, pack {s.pack})")
            t = time.perf_counter()
            try:
                v, detail = run_verdict(g, i["patch"], save_file=save, values=values_for(s.id),
                                        may_run=i["may_run"])
            except PatchError as exc:
                v, detail = "unknown", f"done_command not run: {exc}"
            timings[s.id] = time.perf_counter() - t
            cmd = i["patch"].run.get("done_command") if i["patch"].done is None else None
            if cmd and not detail.startswith("done_command not run"):     # status ran a program: say which
                detail += f"; runs `{' '.join(str(x) for x in cmd)}` to check"
            if v == "done":
                s.will_run, s.reason = False, f"done: {detail}"
            else:
                s.reason = f"{v}: {detail}"

    # ---- a step whose prerequisite does not run does not run either
    changed = True
    while changed:
        changed = False
        skipped = {s.id for s in steps if not s.will_run}
        for s in steps:
            need = [r for r in info[s.id]["requires"] if r in skipped]
            if s.will_run and need:
                s.will_run, s.reason, changed = False, skipped_needs(need), True

    # ---- the built-in rules' detectors (read only): needed or done, before anything runs
    detected, builtin = None, {r.id for r in REGISTRY}
    run_builtin = [s for s in steps if s.will_run and s.id in builtin and s.pack == shipped.id]
    recheck_ids = [s.id for s in steps if s.reason == RECHECK]
    if detect and recheck_ids and rec is not None:
        done_by = _recorded_tool_version(rec)
        if done_by and compare_versions(done_by, _tool_version()) != -1:
            notes.append(f"re-check skipped: the record of {rec.get('label', '?')} says this tool "
                         f"({done_by}) updated it")
            recheck_ids = []
    # ---- R19's layouts (the gene folders only, never the save): source, reference and target, and portraits_version
    dna_setup, faces = None, []
    r19 = next((s for s in steps if s.id == "R19"), None)
    if game is not None and r19 is not None and not no_dna and (r19.will_run or r19.reason == RECHECK):
        from . import dna as D
        ref_meta = read_light(Path(ref.path)).meta if ref.path else None
        dna_setup = D.setup(save_meta=light.meta, game_dir=game.path, old_game_dir=old_game_dir,
                            reference_meta=ref_meta, portrait_mods_given=portrait_mods, target_version=gv,
                            old_portrait_mods=old_portrait_mods)
        dna_setup.face_changes = tuple(D.DEFAULT_FACE_CHANGES if face_changes is None else face_changes)  # before
        # any plan is built (Setup caches them); not given: every change (0.4.8), "none": 0.4.0's faces
        faces = _faces_rows(dna_setup, transplanting=bool(chosen & set(TRANSPLANT)))
        notes.extend(dna_setup.notes)
    if not detect or not recheck_ids or refused:
        for s in steps:
            if s.reason == RECHECK:                        # not re-checked: as before, the pack is not selected
                s.reason = skip_why
    if refused and (checks or (detect and (run_builtin or recheck_ids))):
        detected = "not run: the plan is refused (fail early); fix the refusal, then run status again"
    elif detect and (run_builtin or recheck_ids):
        from .detect import Detection, Env, detect as run_detector, has_detector
        refbytes = None
        if ref.path and any(s.id in ("R14", "R16", "R17") for s in run_builtin):
            stage("reading the reference save")
            refbytes = sf.read_save(ref.path).gamestate
        from .lint import workshop_mod_dirs
        env = Env(game_dir=game.path if game else None, reference=refbytes, patches=shipped.patches,
                  mod_dirs=workshop_mod_dirs(light.meta, game.path if game else None), dna=dna_setup)
        g = gamestate()
        # an up-to-date save (djdarcy, 2026-11-01): skip what the record shows applied and what its detector finds
        # done, run what its detector finds needed, and never run blindly what cannot be judged
        applied = _applied_in_record(rec, save, shipped.id) if rec is not None else {}
        transplant_named = bool(set(TRANSPLANT) & named)
        judge = [s for s in run_builtin if s.reason == "runs" or s.reason.startswith("runs (named")]
        judge_ids = [s.id for s in judge] + [
            rid for rid in recheck_ids if rid not in applied and rid not in REPORT_ONLY + SAME_LINE_ONLY
            and not (rid in TRANSPLANT + ("R17",) and not transplant_named)]
        names = {s.id: s.name for s in steps}

        def run_detector_timed(rid: str):
            stage(f"checking {rid} {names.get(rid, '')} ({judge_ids.index(rid) + 1} of {len(judge_ids)})")
            t = time.perf_counter()
            try:
                d = run_detector(rid, g, env)
            finally:
                timings[rid] = time.perf_counter() - t
            if d.left:                                 # what its rule cannot fix: said once, in the notes
                many = sum(int(m.group(1).replace(",", "")) for x in d.left
                           if (m := re.match(r"([\d,]+) ", x))) != 1
                notes.append(f"{rid}: {'; '.join(d.left)}; " + ("they stay as they are" if many else "it stays as it is"))
            notes.extend(f"{rid}: {n}" for n in d.notes)
            return d
        for s in judge:
            s.reason = run_detector_timed(s.id).line()
        for rid in recheck_ids:
            st = next(x for x in steps if x.id == rid)
            if rid in applied:
                st.reason = f"already applied (record: {applied[rid]})"
                continue
            if rid in REPORT_ONLY:
                st.reason = "reports only (no edit): not re-run on an up-to-date save; name it with --rules"
                continue
            if rid in SAME_LINE_ONLY:
                st.reason = "not re-run on a save on the game's line (assumed compatible); name it with --rules"
                continue
            # the transplant is never judged on an up-to-date save: it is "unknown", and what is unknown never runs
            transplant = rid in TRANSPLANT + ("R17",) and not transplant_named
            d = (Detection("unknown", why="the transplant is not judged on an up-to-date save") if transplant
                 else run_detector_timed(rid))
            if d.state == "needed":
                st.will_run, st.reason = True, d.line()
            elif d.state == "done":
                st.reason = d.line()
            else:
                st.reason = ("unknown: not in the record and no detector; name it with --rules to run it"
                             if not transplant and not has_detector(rid, env) else
                             f"unknown: {d.why}, and not in the record; name it with --rules to run it")
        for st in steps:                             # what the re-check started still needs its inputs
            if st.will_run and st.id in recheck_ids and info[st.id]["needs_ref"] and not ref.path:
                st.will_run, st.reason = False, "needs a reference save, and there is none"
        changed = True
        while changed:
            changed = False
            skipped = {x.id for x in steps if not x.will_run}
            for x in steps:
                need = [r for r in info[x.id]["requires"] if r in skipped]
                if x.will_run and need:
                    x.will_run, x.reason, changed = False, skipped_needs(need), True
        detected = "re-checked the save on the game's version line" if recheck_ids else "judged each built-in step"
    elif not detect and (run_builtin or recheck):
        detected = "not run (the plan read only the first megabyte)"

    if same_line and sv["version"] != gv and not covered and compare_versions(sv["version"], gv) == -1:
        notes.append(f"no pack declares {sv['version']} -> {gv} (same {gl[0]}.{gl[1]} line; assumed compatible)")
    already = same_line and not any(s.will_run for s in steps)
    unmet = [s.id for s in steps if s.reason.startswith(("needs --var", "needs the old game"))]
    if already and unmet:
        notes.append(f"nothing runs; {', '.join(unmet)} skipped for an unmet need (see the patches above)")

    out = None
    if in_place:
        out = str(save)
        bak = save.with_name(save.stem + ".bak.ck3")
        notes.append(f"in place: the updated save takes this name, and the original is kept as {bak.name}"
                     + (f" ({bak.name} exists: update refuses to write over it without --force)"
                        if bak.exists() and not force else ""))
    elif output:
        out = str(Path(output))
    elif gv:
        out = str(save.with_name(f"{save.stem}__updated__{gv}.ck3"))
    if out and not in_place and Path(out).exists() and not force:
        notes.append(f"{out} exists: update refuses to write over it without --force")
    p = UpdatePlan(str(save), sv, date, mods, _game(game), [_game(g) for g in installs[1:]], (sv["version"], gv),
                   pack_rows, steps, ref, out, refusals, uncovered, already, notes, light.gamestate_bytes_read,
                   fixes=fixes, record=rec_line, inputs=inputs, prefilled=prefilled, in_place=in_place,
                   prefilled_from=rec.get("label", "?") if prefilled and rec else None,
                   detected=detected, detect_seconds=full.get("seconds") if "g" in full else None,
                   detect_mb=len(full["g"]) / 1e6 if "g" in full else None, detect_timings=timings, seed=seed,
                   cache_note=_cache_note(blockindex.LAST_EVENT), faces=faces)
    p.dna_setup = dna_setup
    p.rules = [rules[s.id] for s in steps if s.will_run]
    p.user_packs = found
    return p


# On an up-to-date save: R6 reports and edits nothing (it would fix nothing it finds), and R7 brings the version to
# the game's, which the same major.minor line does not need (U1: assumed compatible); each runs there only by name
REPORT_ONLY = ("R6",)
SAME_LINE_ONLY = ("R7",)
RECHECK = "re-check: judged by the record and the detectors"


def _applied_in_record(rec: dict, save: Path, pack_id: str) -> dict[str, str]:
    """rule id -> the date of the record's update that applied it to this save game: a row whose input is this
    save, or one made before this save was written (this save then descends from that update's output)."""
    import datetime as _dt
    try:
        written = _dt.datetime.fromtimestamp(save.stat().st_mtime).astimezone()
    except OSError:
        written = None
    out: dict[str, str] = {}
    for row in rec.get("update") or []:
        date = str(row.get("date", ""))
        try:
            mine = bool(row.get("input")) and Path(str(row["input"])).resolve() == save.resolve()
        except OSError:
            mine = False
        try:
            earlier = written is not None and _dt.datetime.fromisoformat(date) <= written
        except (TypeError, ValueError):
            earlier = False
        if not (mine or earlier):
            continue
        for pt in row.get("patches") or []:
            if isinstance(pt, dict) and pt.get("pack") == pack_id and pt.get("id"):
                out[pt["id"]] = date[:16].replace("T", " ")
    return out


def _tool_version() -> str:
    from ._version import get_base_version
    return get_base_version()


def _recorded_tool_version(rec: dict) -> str | None:
    """The tool version of the record's newest update ("ck3-save-updater 0.3.17" -> "0.3.17")."""
    rows = rec.get("update") or []
    tool = str(rows[-1].get("tool", "")) if rows else ""
    return tool.split()[-1] if tool.split() else None


# --------------------------------------------------------------------------- the reference save
def _beside_ours(path: Path) -> bool:
    """This tool's output: a report or lint file written beside it."""
    return any(path.with_name(path.stem + suffix).exists() or path.with_suffix(suffix).exists()
               for suffix in (".report.json", ".lint.json"))


def _reference(given: str | None, save: Path, sv: dict, date: str | None, seed: str | None, gv: str | None,
               folder: Path | None) -> Reference:
    env = os.environ.get("CK3_REFERENCE_SAVE")
    for value, how in ((given, "given"), (env, "$CK3_REFERENCE_SAVE")):
        if value is None or value == "":
            continue
        if value.strip().lower() == "none":
            return Reference(None, how, f"{'--reference' if how == 'given' else how} is none")
        p = Path(value).expanduser()
        if not p.is_file():
            raise FileNotFoundError(f"reference save not found: {p} ({'--reference' if how == 'given' else how})")
        return Reference(str(p), how, "named on the command line" if how == "given" else "named by the environment")
    folder = folder if folder is not None else save_games_dir()
    if folder is None or not Path(folder).is_dir():
        return Reference(None, "none", "none given, and no save folder to look in")
    if not gv or not date:
        return Reference(None, "none", "none given; the save folder cannot be searched without the game's version "
                                       "and the save's date")
    cands = []
    for c in sorted(Path(folder).glob("*.ck3")):
        try:
            if sf.same_file(c, save):
                continue
            lc = read_light(c)
        except (OSError, sf.SaveFormatError):
            continue
        if save_versions(lc.meta)["version"] == gv and meta_date(lc.meta) == date:
            cands.append((c, lc))
    if not cands:
        return Reference(None, "none", f"none given, and no save in {folder} was written by {gv} on {date}")
    names = [str(c) for c, _ in cands]
    if seed is None:
        return Reference(None, "refused", "the save's random_seed was not in the first megabyte of its gamestate, so "
                                          "a save that descends from it cannot be told apart from a reference",
                         candidates=names, ambiguous=names)
    left = [(c, lc) for c, lc in cands if lc.random_seed != seed and not _beside_ours(c)]
    dropped = len(cands) - len(left)
    y, m, d = date.split(".")
    bm = re.compile(rf"mod/zz_ref_{re.escape(y)}(?:_{re.escape(m)}_{re.escape(d)})?\.mod$")
    preferred = [(c, lc) for c, lc in left if any(bm.search(x.decode("utf-8", "replace"))
                                                  for x in _MOD.findall(lc.meta))]
    excluded = (f"; {dropped} left out (the save's own random_seed, a save that descends from it, or this tool's "
                "output)" if dropped else "")
    if len(preferred) == 1:
        return Reference(str(preferred[0][0]), "found in the save folder",
                         f"written by {gv} on {date}, with a zz_ref bookmark mod{excluded}", candidates=names)
    if len(left) == 1:
        return Reference(str(left[0][0]), "found in the save folder", f"the one save written by {gv} on {date}"
                                                                      f"{excluded}", candidates=names)
    if not left:
        return Reference(None, "none", f"none given; every save in {folder} written by {gv} on {date} descends from "
                                       "this save or was written by this tool", candidates=names)
    pool = preferred or left
    return Reference(None, "refused", f"{len(pool)} saves written by {gv} on {date} could each be the reference"
                                      f"{excluded}", candidates=names, ambiguous=[str(c) for c, _ in pool])
