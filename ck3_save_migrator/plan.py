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
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import savefile as sf
from .config import disabled_ids
from .discover import GameInstall, compare_versions, discover_games, save_games_dir, save_versions
from .patches import read_pack, rules_from_pack
from .patches.model import span_matches
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
    "start a new game from its bookmark and save at once, before unpausing",
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
    rules: list = field(default_factory=list, repr=False, compare=False)    # the Rule of each step that runs
    user_packs: list = field(default_factory=list, repr=False, compare=False)   # userpacks.UserPack, for the report

    def has_changes(self) -> bool:
        return not self.refusals and not self.already_current and any(s.will_run for s in self.steps)

    def running(self) -> list[str]:
        return [s.id for s in self.steps if s.will_run]

    def as_dict(self) -> dict:
        d = asdict(self)
        d.pop("rules", None)
        d.pop("user_packs", None)
        return d

    def lines(self) -> list[str]:
        v = self.save_versions
        out = [f"save      : {self.save}",
               f"            version {v['version'] or '?'} (save_game_version {v['save_game_version']}, "
               f"portraits_version {v['portraits_version']}), date {self.save_date or '?'}, "
               f"{len(self.save_mods)} mod(s) listed"]
        if self.game:
            out.append(f"game      : {self.game['version'] or 'version unknown'}  {self.game['path']}  "
                       f"(from {self.game['source']})")
        else:
            out.append("game      : none found")
        out += [f"also      : {g['version'] or 'version unknown'}  {g['path']}  (from {g['source']}; not used)"
                for g in self.other_games]
        out.append(f"gap       : {self.gap[0] or '?'} -> {self.gap[1] or '?'}"
                   + ("  (none: the save is at the game's version)" if self.gap[0] and self.gap[0] == self.gap[1]
                      else ""))
        if self.uncovered:
            out.append(f"NOT COVERED: {self.uncovered}")
        r = self.reference
        out.append(f"reference : {r.path} ({r.how}: {r.why})" if r.path else f"reference : none ({r.why})")
        if not r.path and r.skips:
            out.append(f"            without one these skip: {', '.join(r.skips)}; to make one:")
            out += [f"              {i}. {s.format(save=self.save)}" for i, s in enumerate(REFERENCE_STEPS, 1)]
        out.append("packs     :")
        for p in self.packs:
            trust = f", {p.trust}" if p.trust else ""
            out.append(f"  {p.id} ({p.kind}{trust}): {'selected' if p.selected else 'not selected'}: {p.why}")
        out.append("patches   : (in the order they run)")
        width = max((len(s.name) for s in self.steps), default=0)
        for s in self.steps:
            counts = (f"  matched {s.matched:,} edited {s.edited:,}" if s.matched is not None else "")
            out.append(f"  {s.id:4} {s.name:{width}}  {'runs   ' if s.will_run else 'skipped'}  {s.pack:10} "
                       f"{s.reason}{counts}")
        if any(s.will_run and s.matched is None for s in self.steps):
            out.append(f"            edit counts: {NOT_KNOWABLE}")
        out.append(f"output    : {self.output}" if self.output else "output    : none")
        out += [f"note      : {n}" for n in self.notes]
        if self.already_current:
            out.append("already current: the save is at the game's version and no pack selected for it; "
                       "nothing to do")
        out += [f"REFUSED   : {x}" for x in self.refusals]
        return out


def _game(g: GameInstall | None) -> dict | None:
    return None if g is None else {"source": g.source, "path": str(g.path), "version": g.version}


def _span_why(applies: dict | None, sv: str | None, gv: str | None) -> tuple[bool, str, bool]:
    """(selected, why, declares a span that covers this save and game)."""
    if not applies:
        return True, "no version span declared (matches any version)", False
    parts, ok = [], True
    for key, ver in (("save", sv), ("game", gv)):
        span = applies.get(key)
        if span is None:
            parts.append(f"{key}: any")
            continue
        m = span_matches(span, ver)
        ok = ok and bool(m)
        parts.append(f"{key} {ver or '?'} {'matches' if m else 'does not match' if m is False else 'cannot be compared to'}"
                     f" {span}")
    return ok, "; ".join(parts), ok


def _named_ids(spec: str) -> set[str]:
    by = {k.lower(): r.id for r in REGISTRY for k in (r.id, r.name)}
    return {by[t.strip().lower()] for t in spec.split(",")
            if t.strip() and t.strip().lower() != "all" and not t.strip().startswith("-") and t.strip().lower() in by}


def plan_update(save: str | Path, *, game_dir: str | None = None, reference: str | None = None,
                old_game_dir: str | None = None, rules_spec: str | None = None, output: str | None = None,
                packs: list[str] | None = None, allow_run: bool = False, save_folder: Path | None = None,
                force: bool = False) -> UpdatePlan:
    """The plan for updating ``save`` (see the module docstring). Refusals are collected in ``refusals`` (the
    caller exits 1); a bad option (an unknown rule, a broken pack) raises ValueError as ``migrate`` does."""
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
    if game is None:
        refusals.append("no game install found: give --game-dir <the game's 'game' folder>")
    elif gv is None:
        refusals.append(f"the game's version could not be read (no readable launcher/launcher-settings.json in "
                        f"{game.install}); update chooses its packs by version (migrate still works without it)")
    elif compare_versions(sv["version"], gv) == 1:
        refusals.append(f"the save was written by game version {sv['version']}, newer than the game at {game.path} "
                        f"(version {gv}); update brings a save from an older version to the game's")

    # ---- the built-in pack, and the rules --rules selects from it
    spec = rules_spec if rules_spec is not None else "all"
    chosen = {r.id for r in select(spec)}                         # raises ValueError on a bad --rules
    off, named = set(disabled_ids()), _named_ids(spec)
    shipped = read_pack()
    ok, why, covers = _span_why(shipped.applies, sv["version"], gv)
    pack_rows = [PackChoice(shipped.id, "built in", "(inside the package)", ok, why)]
    covered = covers
    steps: list[Step] = []
    rules: dict[str, object] = {}
    ref = _reference(reference, save, sv, date, light.random_seed, gv, save_folder)
    if ref.how == "refused":
        refusals.append(ref.why)
    for r in REGISTRY:
        reason, run = "runs", True
        if not ok:
            reason, run = "its pack is not selected for this save and game", False
        elif r.id not in chosen:
            reason, run = ("opt-in: not in --rules" if not r.default else "not selected by --rules"), False
        elif r.id in off and r.id not in named:
            reason, run = "turned off in your config (`ck3update enable` turns it back on)", False
        elif r.id in NEEDS_REFERENCE and not ref.path:
            reason, run = "needs a reference save, and there is none", False
        elif r.id in NEEDS_OLD_GAME and not old_game_dir:
            reason, run = "needs the old game folder (--old-game-dir), and none was given", False
        steps.append(Step(r.id, r.name, shipped.id, run, reason))
        rules[r.id] = r
    ref.skips = [s.id for s in steps if s.reason.startswith("needs a reference")]

    # ---- your packs, then --pack folders
    ensure_packs_dir()
    extra: list[tuple[object, list[Step]]] = []
    found = find_user_packs().packs
    for up in found:
        ok, why, covers = _span_why(up.pack.applies, sv["version"], gv)
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
                reason = "its pack is not selected for this save and game"
            elif up.state in ("not trusted", "changed since trusted") and not allow_run:
                reason = (f"its pack is {up.state}: `ck3update trust {up.id}` lets it run")
            elif not p.default:
                reason = "default = false"
            elif p.id in off:
                reason = "turned off in your config (`ck3update enable` turns it back on)"
            else:
                reason = "runs"
            own.append(Step(p.id, p.name, up.id, reason == "runs", reason))
            if p.id in built:
                rules[p.id] = built[p.id]
        extra.append((up.pack, own))
    for folder in packs or []:
        pk = read_pack(folder)
        ok, why, covers = _span_why(pk.applies, sv["version"], gv)
        pack_rows.append(PackChoice(pk.id, "--pack", str(folder), ok, why))
        built = {r.id: r for r in rules_from_pack(folder, allow_run=allow_run)} if ok else {}   # refuses code
        covered = covered or (ok and covers)
        own = []
        for p in pk.ordered():
            reason = ("its pack is not selected for this save and game" if not ok else
                      "default = false" if not p.default else "runs")
            own.append(Step(p.id, p.name, pk.id, reason == "runs", reason))
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
        while at + 1 < len(steps) and getattr(steps[at + 1], "_after", None) == pk.after:
            at += 1                                    # several packs after one patch: in loading order
        for s in own:
            s._after = pk.after
        steps[at + 1:at + 1] = own

    # ---- the gap
    uncovered = None
    current = bool(sv["version"]) and sv["version"] == gv
    if gv and sv["version"] and not current and not covered and not refusals:
        uncovered = (f"the gap {sv['version']} -> {gv}: no selected pack declares it covers it (a pack's "
                     "[applies] span); nothing would bring the save to the game's version")
        refusals.append(uncovered)
    already = current and not any(s.will_run for s in steps)

    out = None
    if output:
        out = str(Path(output))
    elif gv:
        out = str(save.with_name(f"{save.stem}__updated_{gv}.ck3"))
    if out and Path(out).exists() and not force:
        notes.append(f"{out} exists: update refuses to write over it without --force")
    p = UpdatePlan(str(save), sv, date, mods, _game(game), [_game(g) for g in installs[1:]], (sv["version"], gv),
                   pack_rows, steps, ref, out, refusals, uncovered, already, notes, light.gamestate_bytes_read)
    p.rules = [rules[s.id] for s in steps if s.will_run]
    p.user_packs = found
    return p


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
        return Reference(None, "refused", f"the save's random_seed was not in the first megabyte of its gamestate, so "
                                          f"a save that descends from it cannot be told apart from a reference; give "
                                          f"--reference (candidates: {', '.join(names)})", candidates=names)
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
    return Reference(None, "refused", f"{len(pool)} saves in {folder} could each be the reference (written by {gv} on "
                                      f"{date}): {', '.join(str(c) for c, _ in pool)}; give one with --reference",
                     candidates=names)
