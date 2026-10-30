"""Command-line entry point for ck3-save-updater: the `ck3update` command (`ck3-save-migrator` is a second name for
it, kept for now).

Exit codes: 0 ok, 1 bad input, 2 refused by a guard (output exists, in-place), 3 verification failed,
4 lint found an error (migrate: the output is still written, for inspection), 5 a patch failed (an ``expect`` that
did not hold, or a run patch's command that failed; migrate writes nothing; check: one would fail). ``tools run``
returns the script's own exit code. ``soak`` (which starts the game): 0 clean exit, 2 refused, 6 a crash, 7 did not
load or did not exit, 8 a guard check failed.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
import time
from pathlib import Path

from dazzle_loglib import (
    DEFAULT, DIAGNOSTICS, ERROR, EXTRA, MINIMAL, WARNING,
    ChannelDef, get_output, init_output, parse_channel_spec, resolve_channel_specs, resolve_verbosity,
)

from ._version import __app_name__, get_display_version
COMMAND = "ck3update"          # what people type; ``ck3-save-migrator`` still runs the same entry point
from .lint import listed_workshop_mods, lint_gamestate, load_game_data, workshop_mod_dirs
from .config import config_path, disabled_ids, trusted_packs, write_disabled, write_trusted
from .userpacks import ensure_packs_dir, find_user_packs, runs_what, user_rules
from .discover import GameInstall, compare_versions, discover_games, find_save, save_versions
from .patches import read_pack, rules_from_pack, verdict
from .patches.model import tomllib
from .refmod import make_bookmark, meta_date, pick_ruler, write_mod
from .rules import REGISTRY, RuleContext, missing_prerequisites, run_rules, select
from .rules.religion_1_20 import custom_faith_names
from .savefile import (
    InPlaceError,
    OutputExistsError,
    SaveFormatError,
    VerifyError,
    default_output,
    read_save,
    same_file,
    sha256,
    write_save,
)


# Output goes through dazzle-loglib (docs/cli-integration.md). Levels on its scale: a command's RESULT is MINIMAL
# (-1, still shown by -q), narration is DEFAULT (0), detail is EXTRA (+1, -v) and DIAGNOSTICS (+2, -vv); errors
# and warnings go to stderr. At the default verbosity the output is what it was before loglib, byte for byte
# (tests/test_cli_output.py against a golden recorded from the print-based CLI). The JSON report is the audit
# record and does not depend on verbosity.
CHANNELS = [
    ChannelDef("rules", "Rules applied, their counts; the rules listing", fd="stdout"),
    ChannelDef("transplant", "The new-map transplant's plan and write counts (R14-R17)", fd="stderr"),
    ChannelDef("lint", "Pre-launch checks: the verdict and the findings", fd="stdout"),
    ChannelDef("io", "Reading and writing saves; what was written, sizes, hashes", fd="stdout"),
    ChannelDef("timing", "Wall time per rule", fd="stderr"),
    ChannelDef("gamediff", "What a game update changed (the gamediff command)", fd="stdout"),
]


def say(level: int, text: str, channel: str, err: bool = False) -> None:
    """One line of output on ``channel``; ``err`` sends it to stderr whatever the channel's destination."""
    get_output().emit(level, text, channel=channel, file="stderr" if err else None)


def add_verbosity_flags(parser: argparse.ArgumentParser, top: bool = False) -> None:
    """The one place the verbosity flags are declared (loglib's recipe), on the main parser AND every
    sub-command, feeding one chain: `-v migrate`, `migrate -v` and `-v migrate -v` (= -vv) all work.

    The main parser's copies write to their own fields (``top_*``) and main() adds the two: with one shared
    field, argparse would let the sub-command's default (0) overwrite a `-v` given before the sub-command."""
    p = "top_" if top else ""
    parser.add_argument("-v", "--verbose", action="count", default=0, dest=p + "verbose",
                        help="more detail (repeatable: -v progress and timing, -vv reads/writes)")
    parser.add_argument("-q", "--quiet", action="count", default=0, dest=p + "quiet",
                        help="less (repeatable: -q results only, -qqq errors only, -qqqq nothing)")
    parser.add_argument("--show", action="append", metavar="CHANNEL[:LEVEL]", type=parse_channel_spec,
                        default=[], dest=p + "show", help="raise one channel, e.g. --show transplant:1 "
                                                          "(channels: rules, transplant, lint, io, timing)")


def read_save_logged(path):
    t = time.perf_counter()
    save = read_save(path)
    say(DIAGNOSTICS, f"read {path}: {sum(len(m.data) for m in save.members):,} bytes inflated in "
                     f"{time.perf_counter() - t:.1f}s", "io", err=True)
    return save


def run_rules_timed(save, rules, ctx):
    """run_rules, one rule at a time, with each rule's wall time on the timing channel (+1)."""
    out = []
    for r in rules:
        t = time.perf_counter()
        out += run_rules(save, [r], ctx)
        say(EXTRA, f"  {r.id:3} {r.name:22} {time.perf_counter() - t:6.1f}s", "timing", err=True)
    return out


def cmd_inspect(args) -> int:
    save = read_save_logged(args.save)
    h = save.header
    newline = "CRLF" if h.newline == b"\r\n" else "LF"   # outside the f-string: 3.10/3.11 forbid backslashes there
    say(MINIMAL, f"file      : {save.source}", "io")
    say(MINIMAL, f"header    : {h.raw.rstrip().decode('ascii')}  (kind {h.kind:02x} {save.kind_name}, "
                 f"meta length {h.meta_len:,}, newline {newline})", "io")
    say(MINIMAL, f"meta block: {len(save.meta):,} bytes", "io")
    for m in save.members:
        say(MINIMAL, f"member    : {m.name}  {len(m.data):,} bytes inflated", "io")
    v = save_versions(save.meta)
    say(MINIMAL, f"versions  : version {v['version'] or '?'}, save_game_version {_or_q(v['save_game_version'])}, "
                 f"portraits_version {_or_q(v['portraits_version'])}", "io")
    for w in save.warnings:
        say(MINIMAL, f"WARNING   : {w}", "io")
    installs = game_installs(args.game_dir)
    if not installs:
        named = args.game_dir if args.game_dir is not None else os.environ.get("CK3_GAME_DIR")
        say(MINIMAL, "game      : none" + (f" ({'--game-dir' if args.game_dir is not None else '$CK3_GAME_DIR'} "
                                             "is none)" if named else " found (give --game-dir)"), "io")
    for i, g in enumerate(installs):
        say(MINIMAL, f"{'game' if i == 0 else 'also':10}: {describe_install(g)}"
                     + ("" if i == 0 else "  (not used: an older or unknown version)"), "io")
    return 0


def _or_q(x) -> str:
    return "?" if x is None else str(x)


def game_installs(explicit: str | None) -> list[GameInstall]:
    """Every game install found (discover.py), newest version first: --game-dir, else $CK3_GAME_DIR, else Steam's
    own records, the usual Steam folders, Steam libraries at a drive's root, and the current folder. ``none``
    (flag or variable) means no game; a folder named that is not a game folder is refused."""
    return discover_games(explicit, os.environ.get("CK3_GAME_DIR"))


def find_game_dir(explicit: str | None) -> Path | None:
    """The game folder used: the newest install ``game_installs`` finds; None when there is none (the rules and
    checks that need one skip)."""
    found = game_installs(explicit)
    return found[0].path if found else None


def describe_install(g: GameInstall) -> str:
    return f"{g.version or 'version unknown'}  {g.path}  (from {g.source})"


def check_save_not_newer(save_version: str | None, game: GameInstall | None) -> None:
    """Refuse (ValueError, exit 1) a save written by a newer game version than the game used; say so when the
    game's version cannot be read, and go on."""
    if game is None:
        return
    if game.version is None:
        say(WARNING, f"WARNING: the game's version is unknown (no readable launcher/launcher-settings.json in "
                     f"{game.install}); the save's version ({save_version or '?'}) was not compared with it",
            "io", err=True)
        return
    if compare_versions(save_version, game.version) == 1:
        raise ValueError(f"the save was written by game version {save_version}, newer than the game at {game.path} "
                         f"(version {game.version}); this tool updates a save from an older version to the game's")


DEV_REFERENCE = Path("private/data/originals/reference-1.20/ref_1_20_987_10_27.ck3")


def find_reference(explicit: str | None) -> Path | None:
    """--reference, else $CK3_REFERENCE_SAVE, else this project's 987 reference save when run from the repo.

    ``--reference none`` means no reference (R8-R12 skip), whatever the environment holds; with no flag,
    ``CK3_REFERENCE_SAVE=none`` means the same.
    """
    env = os.environ.get("CK3_REFERENCE_SAVE")
    if (explicit if explicit is not None else env or "").lower() == "none":
        return None
    for cand in (explicit, env, str(DEV_REFERENCE)):
        if cand and Path(cand).is_file():
            return Path(cand)
    return None


def branch_path(path: Path, shape: str) -> Path:
    """X.migrated.ck3 -> X__wos-<shape>.migrated.ck3; X.report.json -> X__wos-<shape>.report.json; X.json -> X__wos-<shape>.json."""
    name = path.name
    for double in (".migrated.ck3", ".report.json"):
        if name.endswith(double):
            return path.with_name(name[: -len(double)] + f"__wos-{shape}{double}")
    return path.with_name(f"{path.stem}__wos-{shape}{path.suffix}")


def _emit(args, save, results, out: Path, report_path: str | None, ctx, in_sha: str, lint_rep=None) -> None:
    t = time.perf_counter()
    result = write_save(save, out, force=args.force, recompress=args.recompress, dry_run=args.dry_run)
    say(DIAGNOSTICS, f"{'built' if result.dry_run else 'wrote'} {out}: {result.size:,} bytes, verified, in "
                     f"{time.perf_counter() - t:.1f}s", "io", err=True)
    tag = "[dry-run] would write" if result.dry_run else "wrote"
    how = "input bytes reused verbatim" if result.verbatim else "re-deflated"
    say(MINIMAL, f"{tag}: {out}", "io")
    say(DEFAULT, f"  rules applied : {len(results)}" + (f"  (wos shape: {ctx.wos_shape})"
                                                        if any(r.id == 'R10' for r in results) else ""), "rules")
    for r in results:
        note = f"  ({r.extra['skipped']})" if "skipped" in r.extra else ""
        say(DEFAULT, f"    {r.id:3} {r.name:22} matched {r.matched:>8,}  edited {r.edited:>8,}{note}", "rules")
    for r in results:
        if r.id in ("R14", "R15", "R16", "R17") and "skipped" not in r.extra:
            say(EXTRA, f"  {r.id} {r.name}: {_transplant_summary(r)}", "transplant")
    say(DEFAULT, f"  size          : {result.size:,} bytes ({how})", "io")
    say(DEFAULT, f"  meta length   : {result.meta_len:,}", "io")
    say(DEFAULT, f"  sha256        : {result.sha256}", "io")
    say(DEFAULT, f"  gamestate sha : {result.gamestate_sha256}", "io")
    say(DEFAULT, "  verified      : re-read, meta copies equal, length field correct", "io")
    if lint_rep is not None:
        print_lint(lint_rep)
        if not result.dry_run:
            lint_path = out.with_suffix(".lint.json")      # X.migrated.ck3 -> X.migrated.lint.json
            lint_path.write_text(json.dumps(lint_rep.as_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
            say(DEFAULT, f"  lint report   : {lint_path}", "io")
    if report_path:
        report = {
            "tool": f"{__app_name__} {get_display_version()}",
            "input": str(Path(args.save).resolve()), "input_sha256": in_sha,
            "output": None if result.dry_run else str(out.resolve()), "output_sha256": result.sha256,
            "dry_run": result.dry_run, "game_dir": str(ctx.game_dir) if ctx.game_dir else None,
            "game_installs": [{"source": g.source, "path": str(g.path), "version": g.version}
                              for g in ctx.state.get("game_installs", [])],
            "save_versions": ctx.state.get("save_versions"),
            "user_packs": ctx.state.get("user_packs", []),
            "reference": str(ctx.reference) if ctx.reference else None, "wos_shape": ctx.wos_shape,
            "assumptions": [a for r in results for a in r.extra.get("assumptions", [])],
            "lost": [x for r in results for x in r.extra.get("lost", [])],
            "rules": [r.as_dict() for r in results],
            "lint": lint_rep.as_dict() if lint_rep is not None else None,
        }
        Path(report_path).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        say(DEFAULT, f"  report        : {report_path}", "io")


def _transplant_summary(r) -> str:
    """One line per transplant rule for -v: the counts a reader checks first (the full record is the report)."""
    e = r.extra
    if r.id == "R14":
        return (f"{e.get('titles_planned', 0):,} titles, {e.get('provinces_planned', 0):,} provinces planned; "
                f"{e.get('left_to_the_engine_unheld_landless', 0):,} unheld landless titles left to the game")
    if r.id == "R15":
        by = e.get("by_class", {})
        return ", ".join(f"{n} {k}" for k, n in sorted(by.items())) or "nothing to settle"
    if r.id == "R16":
        return (f"{e.get('rulers', 0):,} rulers, {e.get('courtiers', 0):,} courtiers, {e.get('family', 0):,} "
                f"relatives, {e.get('displaced_landless', 0):,} displaced")
    ins = e.get("inserted", {})
    hs = e.get("holy_sites", {})
    return (f"{sum(ins.values()):,} entries written, {e.get('dropped_total', 0):,} links dropped, "
            f"{e.get('seams', 0):,} seams, collisions {e.get('collisions', 0)}, "
            f"holy sites re-attached {hs.get('reattached', 0)}")


def _check_paths(args, outputs: list[tuple[Path, str | None]], *, existence: bool) -> None:
    """Refuse before any work: writing over the input, a missing output folder, an existing output.

    write_save repeats the input/exists guards at write time; these make the refusal immediate.
    """
    src = Path(args.save).resolve()
    for out, report in outputs:
        if same_file(out, src):           # S7: --force never lifts this one (resolved path, then samefile)
            raise InPlaceError(f"refusing to write over the input file: {out}")
        folders = ([] if args.dry_run else [out.parent]) + ([Path(report).parent] if report else [])
        for folder in folders:
            if not (folder if str(folder) else Path(".")).is_dir():
                raise FileNotFoundError(f"output folder does not exist: {folder}")
        if existence and out.exists() and not args.force and not args.dry_run:
            raise OutputExistsError(f"output already exists: {out} (use --force to overwrite)")


def read_patch_vars(pairs: list[str], file: str | None) -> dict:
    """The caller's variables for run patches: ``--vars file.toml`` first, then each ``--var name=value``."""
    out: dict = {}
    if file:
        try:
            data = tomllib.loads(Path(file).read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as exc:
            raise ValueError(f"--vars {file}: not valid TOML: {exc}") from None
        for k, v in data.items():
            if isinstance(v, dict):
                raise ValueError(f"--vars {file}: '{k}' is a table; give a string, a number or a list")
            out[k] = [str(x) for x in v] if isinstance(v, list) else str(v)
    for pair in pairs:
        name, sep, value = pair.partition("=")
        if not sep or not name.strip():
            raise ValueError(f"--var {pair!r}: write it as name=value")
        out[name.strip()] = value
    return out


def load_user_packs(allow_run: bool):
    """The player's own packs (userpacks.py): create the standard folder on the first run, find the packs, say
    which are skipped and why, and return (their rules, the packs found). A skipped pack does not change the exit
    code."""
    ensure_packs_dir()
    found = find_user_packs()
    rules, skipped, skipped_off = user_rules(found, allow_run=allow_run)
    for line in skipped:
        say(WARNING, f"WARNING: {line}", "rules", err=True)
    if skipped_off:
        say(MINIMAL, f"skipped by your config: {', '.join(skipped_off)} (your packs' patches; `ck3update enable "
                     "<id>` turns one back on)", "rules")
    return rules, found.packs


def cmd_migrate(args) -> int:
    out = Path(args.output) if args.output else default_output(args.save)
    # director 2026-10-26 00:45 (S9): no --rules means the defaults, because a user who types `migrate save.ck3`
    # wants a migration; an explicit empty selection is refused (select raises)
    rules = select_rules(args.rules if args.rules is not None else "all",
                         include_off=("R7",) if args.bump_version else ())
    if args.bump_version:
        say(WARNING, "WARNING: --bump-version is deprecated and does nothing: the version bump (R7) is part of the "
                     "default rules", "rules", err=True)
    # the player's own packs (the standard folder, then pack_dirs) run after the selected rules
    user_rules, user_packs = load_user_packs(args.allow_run)
    rules = rules + user_rules
    # patch packs from folders run after those, in the order given (their default patches)
    for folder in args.pack or []:
        rules = rules + [r for r in rules_from_pack(folder, allow_run=args.allow_run) if r.default]
    patch_vars = read_patch_vars(args.var or [], args.vars)
    # S1: a rule whose prerequisites are not selected is refused before any work, naming them
    missing = missing_prerequisites(rules)
    if missing:
        raise ValueError("rule prerequisites missing: " + "; ".join(
            f"{rid} needs {', '.join(need)}" for rid, need in missing)
            + " (add them, or use --rules all,R14,R15,R16 for the full migration with the transplant)")
    shapes = ["faith", "rite"] if args.wos_shape == "both" else [args.wos_shape]
    reference = find_reference(args.reference)
    split = next((i for i, r in enumerate(rules) if r.id == "R10"), None)
    may_branch = split is not None and len(shapes) == 2 and reference is not None

    def outputs(branch: bool) -> list[tuple[Path, str | None]]:
        if not branch:
            return [(out, args.report)]
        return [(branch_path(out, s), str(branch_path(Path(args.report), s)) if args.report else None) for s in shapes]

    # path guards before the save is even read: every output this run could write
    _check_paths(args, outputs(False) + (outputs(True) if may_branch else []), existence=False)
    save = read_save_logged(args.save)
    for w in save.warnings:
        say(WARNING, f"WARNING: {w}", "io", err=True)
    # one output per custom-faith shape only when there is a custom faith to shape; otherwise one plain output
    branch = may_branch and bool(custom_faith_names(save.gamestate))
    _check_paths(args, outputs(branch), existence=True)        # before any rule runs
    installs = game_installs(args.game_dir)
    check_save_not_newer(save_versions(save.meta)["version"], installs[0] if installs else None)
    in_sha = sha256(save.to_bytes())
    ctx = RuleContext(game_dir=installs[0].path if installs else None, portraits_version=args.portraits_version,
                      reference=reference, wos_shape=shapes[0],
                      old_game_dir=Path(args.old_game_dir) if args.old_game_dir else None,
                      expansion_orders=not args.no_expansion_orders)
    ctx.mod_dirs = workshop_mod_dirs(save.meta, ctx.game_dir)     # R23 reads their localization
    ctx.state["game_installs"] = installs                         # the report lists them
    ctx.state["save_versions"] = save_versions(save.meta)
    ctx.state["user_packs"] = [up.as_dict() for up in user_packs]           # the report lists them
    ctx.state["patch_vars"] = patch_vars
    known = None         # what the game and the mods define: read once, shared by both outputs
    ref_gamestate = [None]   # the reference's gamestate, read with `known`: lint compares the save's titles to it
    lint_errors = 0

    def lint_of(s):
        nonlocal known, lint_errors
        if args.no_lint:
            return None
        if known is None:
            ref_g = ref_gamestate[0] = read_save(reference).gamestate if reference else None
            mods, missing = listed_workshop_mods(save.meta, ctx.game_dir) if args.lint_mods == "save" else ([], [])
            known = load_game_data(ctx.game_dir, ref_g, mods, mods_missing=missing,
                                   reference_name=str(reference) if reference else None)
        # the fresh-game title comparison only when the transplant ran: without R14 the save lacks every title the
        # target version added, by the user's choice, and that is not an error in the output
        transplanted = any(r.id == "R14" for r in rules)
        rep = lint_gamestate(s.gamestate, known=known, reference=ref_gamestate[0] if transplanted else None,
                             game_dir=ctx.game_dir)
        lint_errors += rep.errors
        return rep

    def failed(results) -> bool:
        """A patch that failed (an ``expect`` that did not hold, a run command that failed) stops the migration:
        each is printed with its message and nothing is written (exit 5)."""
        bad = [r for r in results if r.extra.get("failed")]
        for r in bad:
            say(ERROR, f"ERROR: patch {r.id} ({r.name}) failed: {r.extra['failed']}", "rules", err=True)
            for line in r.extra.get("stderr") or []:
                say(ERROR, f"    {line}", "rules", err=True)
        if bad:
            say(ERROR, f"ERROR: {len(bad)} patch(es) failed; nothing written", "rules", err=True)
        return bool(bad)

    def nothing_to_write(results) -> bool:
        """S9/S11: every selected rule edited 0 (the save is already at the target, or nothing matched): write
        nothing, say so with the counts, exit 0; --force does not change that."""
        if sum(r.edited for r in results):
            return False
        say(MINIMAL, f"nothing to write: {len(results)} rules ran and edited 0 "
                     f"(matched {sum(r.matched for r in results):,}); the save is already migrated, or nothing in "
                     "it matched", "rules")
        for r in results:
            note = f"  ({r.extra['skipped']})" if "skipped" in r.extra else ""
            say(DEFAULT, f"    {r.id:3} {r.name:22} matched {r.matched:>8,}  edited {r.edited:>8,}{note}", "rules")
        return True

    if not branch:
        results = run_rules_timed(save, rules, ctx)
        if failed(results):
            return 5
        if nothing_to_write(results):
            return 0
        _emit(args, save, results, out, args.report, ctx, in_sha, lint_of(save))
    else:
        # both shapes: run the shared rules once, branch at R10
        shared = run_rules_timed(save, rules[:split], ctx)
        if failed(shared):
            return 5
        runs = []
        for shape in shapes:        # every shape runs before any is written, so a failure leaves no output at all
            s2 = copy.deepcopy(save)
            c2 = copy.copy(ctx)
            c2.state = copy.deepcopy(ctx.state)
            c2.wos_shape = shape
            runs.append((shape, s2, c2, shared + run_rules_timed(s2, rules[split:], c2)))
        if failed([r for *_, results in runs for r in results[len(shared):]]):
            return 5
        for shape, s2, c2, results in runs:
            if nothing_to_write(results):
                continue
            _emit(args, s2, results, branch_path(out, shape),
                  str(branch_path(Path(args.report), shape)) if args.report else None, c2, in_sha, lint_of(s2))
    if lint_errors:
        say(ERROR, f"ERROR: lint found {lint_errors} error(s) in the output; it was written so it can be inspected "
                   "(see the lint lines above)", "lint", err=True)
        return 4
    return 0


def print_lint(rep, indent: str = "  ", level: int = DEFAULT) -> None:
    """The lint verdict and findings. ``level`` is DEFAULT inside migrate (narration) and MINIMAL for the lint
    command, where they are the result; the finding details stay at the same level for now (they may move to
    EXTRA once the plain output has been seen, director 2026-10-25)."""
    say(level, f"{indent}lint          : {rep.errors} error(s), {rep.count('warn')} warning(s), "
               f"{rep.count('reject')} family(ies) 1.20 will log, {rep.count('info')} info", "lint")
    missing = rep.stats.get("mods_not_installed")
    if missing:
        say(DEFAULT, f"{indent}  {len(missing)} mod(s) the save lists are not installed, so these checks leave "
                     f"them out: {', '.join(missing)}", "lint")
    order = {"error": 0, "warn": 1, "reject": 2, "info": 3}
    for f in sorted(rep.findings, key=lambda f: order.get(f.severity, 9)):
        say(level, f"{indent}  {f.severity.upper():6} {f.gloss or f.check}: {f.count:,}", "lint")
        if f.gloss:     # the game's own wording (the check's name) stays visible, so it can be found in error.log
            say(level, f"{indent}          {'game log' if f.severity == 'reject' else 'check'}: {f.check}", "lint")
        for ex in f.examples[:5 if f.severity != 'info' else 12]:
            say(level, f"{indent}          {ex}", "lint")
        if f.note and f.severity != "info":
            say(level, f"{indent}          ({f.note})", "lint")
    for s in rep.skipped:
        say(DEFAULT, f"{indent}  skipped: {s}", "lint")


def run_lint(save, args, reference_path: Path | None):
    game_dir = find_game_dir(getattr(args, "game_dir", None))
    if getattr(args, "no_keys", False):
        return lint_gamestate(save.gamestate, keys=False, game_dir=game_dir)
    reference = read_save(reference_path).gamestate if reference_path else None
    mods, missing = listed_workshop_mods(save.meta, game_dir) if getattr(args, "mods", "save") == "save" else ([], [])
    data = load_game_data(game_dir, reference, mods, mods_missing=missing,
                          reference_name=str(reference_path) if reference_path else None)
    return lint_gamestate(save.gamestate, known=data, reference=reference, game_dir=game_dir)


def cmd_lint(args) -> int:
    save = read_save_logged(args.save)
    for w in save.warnings:
        say(WARNING, f"WARNING: {w}", "io", err=True)
    rep = run_lint(save, args, find_reference(args.reference))
    say(MINIMAL, f"lint: {save.source}", "lint")
    print_lint(rep, level=MINIMAL)
    if args.json:
        Path(args.json).write_text(json.dumps(rep.as_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        say(DEFAULT, f"  report        : {args.json}", "io")
    return 4 if rep.errors else 0


def find_rule(token: str):
    """The registered rule a token names (its id or its name, any case); unknown ones are refused, listing the
    known ids."""
    rule = next((r for r in REGISTRY if token.strip().lower() in (r.id.lower(), r.name.lower())), None)
    if rule is None:
        raise ValueError(f"unknown rule {token!r}; known: {', '.join(f'{r.id}={r.name}' for r in REGISTRY)}")
    return rule


def select_rules(spec: str, include_off: tuple[str, ...] = ()) -> list:
    """``rules.select`` with the player's config applied: a rule turned off (``disable``) is left out of ``all``
    and the leaving out is said in one line; a rule named in ``spec`` runs anyway (an explicit choice beats the
    config)."""
    rules = select(spec, include_off=include_off)
    off = set(disabled_ids())
    if not off:
        return rules
    named = {find_rule(t).id for t in spec.split(",")
             if t.strip() and t.strip().lower() != "all" and not t.strip().startswith("-")}
    named |= {find_rule(t).id for t in include_off}
    skipped = [r.id for r in rules if r.id in off and r.id not in named]
    if skipped:
        say(MINIMAL, f"skipped by your config: {', '.join(skipped)} (name it in --rules to run it anyway, or "
                     "`ck3update enable <id>`)", "rules")
    return [r for r in rules if r.id not in skipped]


GAMEDIFF_SHOWN = 30          # keys listed per line before "... and N more (see --json)"


def _keys_line(keys: list[str]) -> str:
    more = len(keys) - GAMEDIFF_SHOWN
    return ", ".join(keys[:GAMEDIFF_SHOWN]) + (f", ... and {more} more (see --json)" if more > 0 else "")


def cmd_gamediff(args) -> int:
    """Two game folders compared by definition; with --save, which removed or changed keys the save names. Reads
    only; writes nothing but --json."""
    from . import gamediff as gd
    old, new = Path(args.old), Path(args.new)
    a, b = gd.read_definitions(old), gd.read_definitions(new)
    diffs = gd.compare(a, b)
    say(MINIMAL, f"compared {old} ({a.files} files) with {new} ({b.files} files)", "gamediff")
    for group, d in diffs.items():
        say(MINIMAL, f"{group}: {len(d.added)} added, {len(d.removed)} removed, {len(d.changed)} changed", "gamediff")
        for label, keys in (("added", d.added), ("removed", d.removed), ("changed", d.changed)):
            if keys:
                say(DEFAULT, f"  {label:8}: {_keys_line(keys)}", "gamediff")
    totals = [sum(len(getattr(d, k)) for d in diffs.values()) for k in ("added", "removed", "changed")]
    say(MINIMAL, f"total: {totals[0]} added, {totals[1]} removed, {totals[2]} changed, in {len(diffs)} folder(s)",
        "gamediff")
    report = {"old": str(old), "new": str(new), "files": {"old": a.files, "new": b.files},
              "groups": {g: d.as_dict() for g, d in diffs.items()}}
    if args.save:
        save = read_save(args.save)
        uses = gd.used_by_save(diffs, gd.save_names(save.gamestate))
        n = sum(len(v["removed"]) + len(v["changed"]) for v in uses.values())
        say(MINIMAL, f"the save names {n} of the removed or changed keys ({args.save}):", "gamediff")
        for kind, v in uses.items():
            for label in ("removed", "changed"):
                if v[label]:
                    say(MINIMAL, f"  {kind:10} {label:8}: {_keys_line(v[label])}", "gamediff")
        if not uses:
            say(MINIMAL, "  none: nothing it names was removed or changed", "gamediff")
        report["save"] = {"path": str(args.save), "uses": uses}
    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
        say(DEFAULT, f"  report        : {args.json}", "io")
    return 0


SOAK_EXIT = {"clean exit": 0, "crash on exit": 6, "crash while running": 6, "did not load": 7, "did not exit": 7}


def cmd_soak(args) -> int:
    """Load a save in the game, run it, close it through Exit to Desktop, say how it ended (soak.py). STARTS THE
    GAME. Exit 0 clean exit, 2 refused (nothing changed), 6 a crash, 7 did not load or did not exit, 8 a guard check
    failed (an autosave or dlc_load.json not put back: the run folder holds the originals)."""
    from . import soak as sk
    if args.game:
        install = Path(args.game)
    else:
        game = find_game_dir(None)
        if game is None:
            say(ERROR, "ERROR: no game install found; give --game <the folder that holds 'binaries' and 'game'>",
                "io", err=True)
            return 2
        install = game.parent
    exit_after = args.exit_after if args.exit_after is not None else int(args.minutes * 60)
    try:
        res = sk.soak(Path(args.save), install=install, docs=Path(args.docs) if args.docs else None,
                      run_dir=Path(args.run_dir) if args.run_dir else None, exit_after=exit_after,
                      speed=args.speed, mods=args.mods, say=lambda m: say(DEFAULT, f"  {m}", "io"))
    except sk.SoakRefused as exc:
        say(ERROR, f"ERROR: soak refused: {exc}", "io", err=True)
        return 2
    say(MINIMAL, f"soak: {res.outcome}{' (' + res.detail + ')' if res.detail else ''}", "io")
    for what, ok in res.checks:
        say(MINIMAL if ok else ERROR, f"  {what}: {'put back and verified' if ok else 'NOT VERIFIED'}", "io",
            err=not ok)
    say(MINIMAL, f"  run folder: {res.run_dir}", "io")
    if not all(ok for _, ok in res.checks):
        return 8
    return SOAK_EXIT.get(res.outcome, 7)


def cmd_check(args) -> int:
    """Each selected patch's verdict on this save, read only: needed, done, unknown (code and run patches, and
    Python rules with no declarative patch in the shipped pack) or fails (exit 5). Each is judged on the save as it
    is, not after the patches before it."""
    rules = select_rules(args.rules if args.rules is not None else "all")
    save = read_save_logged(args.save)
    for w in save.warnings:
        say(WARNING, f"WARNING: {w}", "io", err=True)
    g = save.gamestate
    ctx = RuleContext(portraits_version=args.portraits_version)
    shipped = read_pack().patches
    rows = []
    for r in rules:
        p = shipped.get(r.id)
        if p is not None and p.kind == "declarative":
            rows.append((r.id, r.name, *verdict(g, p, ctx)))
        else:
            rows.append((r.id, r.name, "unknown", "a Python rule: only running it would tell"))
    # the player's own packs, read only like --pack folders (no code of theirs is imported or run)
    ensure_packs_dir()
    off = set(disabled_ids())
    for up in find_user_packs().packs:
        rows += [(p.id, p.name, *verdict(g, p, ctx)) for p in up.pack.ordered() if p.default and p.id not in off]
    for folder in args.pack or []:
        pack = read_pack(folder)                  # read only: no code of the pack is imported or run
        rows += [(p.id, p.name, *verdict(g, p, ctx)) for p in pack.ordered() if p.default]
    width = max((len(name) for _, name, _, _ in rows), default=0)
    for pid, name, v, detail in rows:
        say(MINIMAL, f"  {pid:4} {name:{width}}  {v:7}  {detail}", "rules")
    counts = {k: sum(1 for row in rows if row[2] == k) for k in ("needed", "done", "unknown", "fails")}
    say(MINIMAL, f"{len(rows)} patch(es): {counts['needed']} needed, {counts['done']} done, {counts['unknown']} "
                 f"unknown, {counts['fails']} fail(s)", "rules")
    if counts["fails"]:
        say(ERROR, f"ERROR: {counts['fails']} patch(es) would fail on this save (see the lines marked fails)",
            "rules", err=True)
        return 5
    return 0


def find_rule_or_user_patch(token: str):
    """A built-in rule, else a patch of the player's own packs, by id or name (any case); refused when neither."""
    t = token.strip().lower()
    if not any(t in (r.id.lower(), r.name.lower()) for r in REGISTRY):
        for up in find_user_packs().packs:
            p = next((p for p in up.pack.ordered() if t in (p.id.lower(), p.name.lower())), None)
            if p is not None:
                return p
    return find_rule(token)


def cmd_disable(args) -> int:
    rule = find_rule_or_user_patch(args.rule)
    ids = disabled_ids()
    path = write_disabled(ids + [rule.id])
    note = "was already turned off" if rule.id in ids else "is turned off"
    say(MINIMAL, f"{rule.id} ({rule.name}) {note}: `--rules all` leaves it out (config: {path})", "rules")
    return 0


def cmd_enable(args) -> int:
    rule = find_rule_or_user_patch(args.rule)
    ids = disabled_ids()
    if rule.id not in ids:
        say(MINIMAL, f"{rule.id} ({rule.name}) was not turned off; nothing to change", "rules")
        return 0
    path = write_disabled([i for i in ids if i != rule.id])
    say(MINIMAL, f"{rule.id} ({rule.name}) is turned back on (config: {path})", "rules")
    return 0


def cmd_disabled(args) -> int:
    ids = disabled_ids()
    names = {r.id: r.name for r in REGISTRY}
    names.update({p.id: p.name for up in find_user_packs().packs for p in up.pack.ordered()})
    for i in ids:
        say(MINIMAL, f"{i:4} {names.get(i, '(not a known rule)')}", "rules")
    if not ids:
        say(MINIMAL, "no rules are turned off", "rules")
    say(DEFAULT, f"(config: {config_path()})", "rules")
    return 0


def cmd_rules(args) -> int:
    for r in REGISTRY:
        flag = "" if r.default else "  (opt-in)"
        say(MINIMAL, f"{r.id:3} {r.name:22} since {r.since:28} {r.description}{flag}", "rules")
    ensure_packs_dir()
    for up in find_user_packs().packs:
        for p in up.pack.ordered():
            flag = "" if p.default else ", opt-in"
            say(MINIMAL, f"{p.id:3} {p.name:22} since {p.since:28} {p.title}  (your pack {up.id}: {up.state}{flag})",
                "rules")
    return 0


def cmd_packs(args) -> int:
    """Each of the player's own packs found: folder, id, kind and whether it runs."""
    ensure_packs_dir()
    found = find_user_packs()
    for base, which, exists in found.scanned:
        say(MINIMAL, f"folder: {base}  ({which}{'' if exists else ', not found'})", "rules")
    width = max((len(up.id) for up in found.packs), default=0)
    for up in found.packs:
        say(MINIMAL, f"  {up.id:{width}}  {up.kind:11}  {up.state:21}  {up.folder}", "rules")
    for p in found.not_packs:
        say(MINIMAL, f"  (not a pack: no pack.toml)  {p}", "rules")
    if not found.packs:
        say(MINIMAL, "no packs of your own yet: see the README in the folder above", "rules")
    return 0


def _user_pack(pack_id: str):
    found = find_user_packs()
    up = next((u for u in found.packs if u.id == pack_id), None)
    if up is None:
        known = ", ".join(u.id for u in found.packs) or "none"
        raise ValueError(f"no pack of yours has the id {pack_id!r} (found: {known}; `ck3update packs` lists them)")
    return up


def cmd_trust(args) -> int:
    ensure_packs_dir()
    up = _user_pack(args.pack)
    trusted = trusted_packs()
    path = write_trusted({**trusted, up.id: up.hash})
    if up.kind == "declarative":
        say(MINIMAL, f"{up.id} runs no code (edits only); it runs without trust. Recorded anyway (config: {path})",
            "rules")
        return 0
    say(MINIMAL, f"{up.id} ({up.folder}) is trusted as its files are now (config: {path}). It runs:", "rules")
    for line in runs_what(up):
        say(MINIMAL, f"  {line}", "rules")
    say(MINIMAL, "If any file of the pack changes, it stops running until you trust it again.", "rules")
    return 0


def cmd_untrust(args) -> int:
    trusted = trusted_packs()
    if args.pack not in trusted:
        say(MINIMAL, f"{args.pack} was not trusted; nothing to change", "rules")
        return 0
    path = write_trusted({k: v for k, v in trusted.items() if k != args.pack})
    say(MINIMAL, f"{args.pack} is no longer trusted: its code patches will not run (config: {path})", "rules")
    return 0


def cmd_tools(args) -> int:
    """The optional tools add-on (tools.py): list, run or locate the standalone scripts. Exit 2 when it cannot
    start (no dazzlecmd-lib, no scripts folder, no such tool); ``run`` otherwise returns the script's exit code."""
    from . import tools
    if not tools.library_available():
        say(ERROR, tools.INSTALL_HINT, "io", err=True)
        return 2
    folder = tools.scripts_dir(args.scripts_dir)
    if folder is None:
        say(ERROR, "ERROR: no scripts folder: give --scripts-dir <folder> or set CK3SM_SCRIPTS_DIR (the source "
                   "checkout's tests/one-offs is used only when running from one)", "io", err=True)
        return 2
    try:
        if args.verb == "list":
            found = tools.list_tools(folder)
            width = max((len(t.name) for t in found), default=0)
            for t in found:
                say(MINIMAL, f"{t.name:{width}}  {t.description}".rstrip(), "io")
            return 0
        if args.verb == "path":
            say(MINIMAL, str(tools.find(folder, args.name).path), "io")
            return 0
        return tools.run(folder, tools.cache_dir(args.cache_dir), args.name, args.args)
    except tools.ToolsError as exc:
        say(ERROR, f"ERROR: {exc}", "io", err=True)
        return 2


RULER_FLAGS = ("character", "title", "culture", "religion", "house", "birth")


def cmd_reference_mod(args) -> int:
    if (args.date is None) == (args.save is None):
        raise ValueError("give the date with --date, or a save to read it from with --save (one of the two)")
    date = args.date if args.date is not None else meta_date(read_save(args.save).meta)
    if args.save is not None:
        say(DEFAULT, f"date: {date} (meta_date of {args.save})", "io")
    given = {k: getattr(args, k) for k in RULER_FLAGS if getattr(args, k) is not None}
    fields = dict(given, female=args.female, name=args.name or "", government=args.government or "feudal_government")
    if len(given) < len(RULER_FLAGS):
        # the missing fields come from the game's history files: the ruler given with --character, else one picked
        game = find_game_dir(args.game_dir)
        if game is None:
            raise ValueError("no game folder to pick the ruler from: give --game-dir, or every one of "
                             + ", ".join(f"--{k}" for k in RULER_FLAGS))
        pick = pick_ruler(game, date, character=given.get("character"))
        found = {"character": pick.character, "title": pick.title, "culture": pick.culture,
                 "religion": pick.religion, "house": pick.house, "birth": pick.birth}
        missing = [k for k in RULER_FLAGS if k not in given and not found[k]]
        if missing:
            raise ValueError(f"character {pick.character}'s history has no {', '.join(missing)}; give "
                             + ", ".join(f"--{k}" for k in missing))
        fields = {**found, **given, "female": args.female or pick.female, "name": args.name or pick.name,
                  "government": args.government or pick.government}
        say(MINIMAL, f"ruler: character {pick.character}"
                     + (f" ({pick.name})" if pick.name else "") + f", {fields['title']}: {pick.why}", "io")
        overridden = [k for k in given if k != "character"]
        if overridden:
            say(DEFAULT, "  given on the command line, so not read from the history: "
                         + ", ".join(f"--{k}" for k in overridden), "io")
    b = make_bookmark(date=date, **fields)
    for p in write_mod(b, Path(args.out)):
        say(MINIMAL, f"wrote: {p}", "io")
    say(MINIMAL, f"next: enable '{b.folder}' in the game's launcher, start a new game from the bookmark "
                 f"'{b.date} Reference (ck3update)' and save at once (do not unpause)", "io")
    say(MINIMAL, "then: pass that save to migrate as --reference (see docs/reference-save.md)", "io")
    return 0


SAVE_HELP = "a save file, or the name of one in the game's 'save games' folder (with or without .ck3)"
GAME_DIR_HELP = ("the game's 'game' folder (default: $CK3_GAME_DIR, else found through Steam's own records and "
                 "the usual Steam folders; 'inspect' lists what it finds; 'none' for no game)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=COMMAND, description="Migrate old Crusader Kings III saves forward to the current game version: inspect, patch, and revive .ck3 save files")
    parser.add_argument("--version", action="version", version=f"{__app_name__} {get_display_version()}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("inspect", help="show a save's header, meta block, zip members and versions, and the game "
                                       "installs found")
    p.add_argument("save", help=SAVE_HELP)
    p.add_argument("--game-dir", help=GAME_DIR_HELP)
    p.set_defaults(func=cmd_inspect)

    p = sub.add_parser("migrate", help="read a save and write a migrated copy (never in place)")
    p.add_argument("save", help=SAVE_HELP)
    p.add_argument("-o", "--output", help="output path (default: <name>.migrated.ck3 beside the input)")
    p.add_argument("--dry-run", action="store_true", help="build and verify in memory; write nothing")
    p.add_argument("--force", action="store_true", help="overwrite an existing output file")
    p.add_argument("--recompress", action="store_true",
                   help="re-deflate the zip even when nothing changed (default reuses the input bytes)")
    p.add_argument("--rules", help="'all' (the default), a comma list of rule ids/names (e.g. R1,title-names), or "
                                   "both: 'all,R14,R15,R16' adds the new-map transplant; a '-' before an id or name "
                                   "leaves that rule out: 'all,-R21', or '-R21' alone for all but R21")
    p.add_argument("--report", help="write a JSON report of the rules' counts to this path")
    p.add_argument("--bump-version", action="store_true",
                   help="deprecated, does nothing: R7 (version bump) is part of the default rules")
    p.add_argument("--portraits-version", type=int, help="R7 also sets portraits_version to this")
    p.add_argument("--reference", help="a save written by the target game version, for R8-R12 "
                   "(default: $CK3_REFERENCE_SAVE, else the project's 987 reference)")
    p.add_argument("--wos-shape", choices=("faith", "rite", "both"), default="both",
                   help="R10: custom faiths as their own faith, as a rite of their template's faith, "
                        "or both (default: two outputs, <stem>__wos-faith / __wos-rite, when a reference is "
                        "given; a save without custom faiths yields one output)")
    p.add_argument("--game-dir", help=GAME_DIR_HELP)
    p.add_argument("--old-game-dir",
                   help="the 'game' folder of the version the save was made with; R15 reads its map to find "
                        "what the current map calls the land of titles it no longer has")
    p.add_argument("--no-expansion-orders", action="store_true",
                   help="R14: leave out the target version's new holy orders that would lease the save's own land "
                        "(by default they are added as the target game has them, and reported)")
    p.add_argument("--no-lint", action="store_true",
                   help="skip the checks run on each output before it is written (see the lint command)")
    p.add_argument("--lint-mods", choices=("save", "none"), default="save",
                   help="which mods the lint assumes will be active when the save loads: the Workshop mods the "
                        "save lists (default; those installed), or none (a vanilla load)")
    p.add_argument("--pack", action="append", metavar="FOLDER",
                   help="a patch pack folder to apply after the selected rules (repeatable, applied in the order "
                        "given; see docs/writing-a-patch.md)")
    p.add_argument("--var", action="append", metavar="NAME=VALUE",
                   help="a variable for the packs' run patches, @@NAME@@ in their command (repeatable)")
    p.add_argument("--vars", metavar="FILE",
                   help="a TOML file of variables for the packs' run patches (a list value becomes several arguments)")
    p.add_argument("--allow-run", action="store_true",
                   help="let script and run patches in --pack folders run their code (it runs with your "
                        "permissions)")
    p.set_defaults(func=cmd_migrate)

    p = sub.add_parser("lint", help="check a 1.20-layout save before loading it: structure, cross-references, "
                                    "unknown keys (exit 4 when an error is found)")
    p.add_argument("save", help=SAVE_HELP)
    p.add_argument("--reference", help="a save written by the target game version, for the key-name check "
                   "(default: $CK3_REFERENCE_SAVE, else the project's 987 reference; 'none' to skip)")
    p.add_argument("--game-dir", help=GAME_DIR_HELP)
    p.add_argument("--no-keys", action="store_true",
                   help="skip the checks that need game data: key names and what 1.20 will log")
    p.add_argument("--mods", choices=("save", "none"), default="save",
                   help="which mods to assume active when the save loads: the Workshop mods the save lists "
                        "(default; those installed), or none (a vanilla load)")
    p.add_argument("--json", help="write the findings to this JSON file")
    p.set_defaults(func=cmd_lint)

    p = sub.add_parser("rules", help="list the migration rules")
    p.set_defaults(func=cmd_rules)

    p = sub.add_parser("gamediff", help="compare two game folders definition by definition (what a game update "
                                        "added, removed and changed), and with --save which of it a save uses; "
                                        "reads only")
    p.add_argument("old", help="the older install's 'game' folder")
    p.add_argument("new", help="the newer install's 'game' folder")
    p.add_argument("--save", help="also say which removed or changed keys this save names (traits, titles, "
                                  "faiths, cultures, modifiers, buildings, game rules)")
    p.add_argument("--json", help="write the whole comparison (every key) to this JSON file")
    p.set_defaults(func=cmd_gamediff)

    p = sub.add_parser("soak", help="START THE GAME: load a save, let it run unpaused, close it through Exit to "
                                    "Desktop, and say whether it exited cleanly or crashed (Windows; see docs/soak.md)")
    p.add_argument("save", help=SAVE_HELP)
    p.add_argument("--game", help="the CK3 install folder, the one holding 'binaries' and 'game' (default: the "
                                  "newest install found, as 'inspect' lists them)")
    p.add_argument("--docs", help="the game's documents folder (default: ~/Documents/Paradox Interactive/"
                                  "Crusader Kings III)")
    p.add_argument("--minutes", type=float, default=10, help="how long the game runs once it is in game (default 10)")
    p.add_argument("--exit-after", type=int, metavar="SECONDS",
                   help="the same in seconds; overrides --minutes")
    p.add_argument("--speed", type=int, default=5, choices=range(1, 6), metavar="1..5",
                   help="the game speed it runs at (default 5)")
    p.add_argument("--mods", nargs="+", metavar="DESCRIPTOR",
                   help="enable exactly these mods for the run (e.g. mod/ugc_2220098919.mod), through dlc_load.json, "
                        "which is put back byte for byte afterwards")
    p.add_argument("--run-dir", help="where the backups, the timeline and copies of the game's logs go (default: a "
                                     "new folder in the tool's cache folder)")
    p.set_defaults(func=cmd_soak)

    p = sub.add_parser("check", help="say, for each selected patch, whether this save needs it, has it done, "
                                     "cannot be told (code and run patches) or would fail; reads only, writes "
                                     "nothing (exit 5 when one would fail)")
    p.add_argument("save", help=SAVE_HELP)
    p.add_argument("--rules", help="as for migrate: 'all' (the default, less the rules turned off with disable), "
                                   "a comma list of ids or names, or both; '-R21' leaves R21 out")
    p.add_argument("--pack", action="append", metavar="FOLDER",
                   help="also check a patch pack folder's default patches (repeatable); nothing in it is run")
    p.add_argument("--allow-run", action="store_true",
                   help="accepted so a migrate command line works unchanged; check runs no patch code, so it "
                        "changes nothing")
    p.add_argument("--portraits-version", type=int, help="as for migrate: R7 also sets portraits_version to this")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("disable", help="turn a rule off: --rules all leaves it out from now on (naming it in "
                                       "--rules still runs it); saved in your config file")
    p.add_argument("rule", help="the rule's id or name, e.g. R21 or dead-liege-cycles")
    p.set_defaults(func=cmd_disable)

    p = sub.add_parser("enable", help="turn a rule that was turned off with disable back on")
    p.add_argument("rule", help="the rule's id or name")
    p.set_defaults(func=cmd_enable)

    p = sub.add_parser("disabled", help="list the rules turned off, and where the config file is "
                                        "($CK3SM_CONFIG overrides it)")
    p.set_defaults(func=cmd_disabled)

    p = sub.add_parser("packs", help="list your own packs (the packs folder beside the config file, and pack_dirs): "
                                     "folder, id, kind and whether each runs")
    p.set_defaults(func=cmd_packs)

    p = sub.add_parser("trust", help="let one of your packs that runs code run on every update, as its files are "
                                     "now; prints what it runs")
    p.add_argument("pack", help="the pack's id (its pack.toml's id; `ck3update packs` lists them)")
    p.set_defaults(func=cmd_trust)

    p = sub.add_parser("untrust", help="take back the trust given to one of your packs")
    p.add_argument("pack", help="the pack's id")
    p.set_defaults(func=cmd_untrust)

    p = sub.add_parser("tools", help="optional add-on: list and run the standalone scripts as they are "
                                     "(needs the [tools] extra; see docs/tools.md)")
    p.add_argument("--scripts-dir", metavar="FOLDER",
                   help="the scripts folder (default: $CK3SM_SCRIPTS_DIR, else the source checkout's tests/one-offs)")
    p.add_argument("--cache-dir", metavar="FOLDER",
                   help="where the tool listing for dazzlecmd-lib is generated (default: $CK3SM_TOOLS_CACHE, else "
                        "the user cache folder)")
    verbs = p.add_subparsers(dest="verb", required=True)
    verbs.add_parser("list", help="each script's name and the first line of its docstring")
    v = verbs.add_parser("run", help="run a script with the arguments given, as its own process; its exit code")
    v.add_argument("name")
    v.add_argument("args", nargs=argparse.REMAINDER, help="passed to the script unchanged")
    v = verbs.add_parser("path", help="the script's full path")
    v.add_argument("name")
    p.set_defaults(func=cmd_tools)

    p = sub.add_parser("reference-mod", help="write a bookmark mod that starts a 1.20 game on your campaign's "
                                             "date, to make a --reference save from (docs/reference-save.md)")
    p.add_argument("--date", help="the campaign's date, YYYY.M.D (e.g. 987.10.27)")
    p.add_argument("--save", help="read the date from this save's metadata (meta_date) instead of --date")
    p.add_argument("--game-dir", help="the game's 'game' folder, whose history files the ruler is picked from "
                                      "(default: the newest install found, as 'inspect' lists them)")
    ruler = " (default: picked from the game's history files)"
    p.add_argument("--character", help="history id of a ruler alive on that date (game/history/characters)" + ruler)
    p.add_argument("--title", help="a title that ruler holds on that date (game/history/titles)" + ruler)
    p.add_argument("--culture", help="the ruler's culture key (e.g. irish)" + ruler)
    p.add_argument("--religion", help="the ruler's faith key (e.g. insular_celtic)" + ruler)
    p.add_argument("--house", help="the ruler's dynasty house key (e.g. house_british_isles_briain)" + ruler)
    p.add_argument("--birth", help="the ruler's birth date, YYYY.M.D" + ruler)
    p.add_argument("--female", action="store_true", help="the ruler is a woman (default: from the history)")
    p.add_argument("--name", help="the name shown on the bookmark screen (default: the history's name, else "
                                  "'Character <history id>')")
    p.add_argument("--government", help="the ruler's government key (default: the title's history, else "
                                        "feudal_government)")
    p.add_argument("--out", required=True, help="the folder to write the mod into (e.g. the game's mod folder)")
    p.set_defaults(func=cmd_reference_mod)
    # the verbosity flags before and after the sub-command, one chain (see add_verbosity_flags)
    add_verbosity_flags(parser, top=True)
    for sp in sub.choices.values():
        add_verbosity_flags(sp)
    return parser


def join_rules_value(argv: list[str]) -> list[str]:
    """``--rules -R21`` as ``--rules=-R21``: argparse would take a value starting with '-' for an option."""
    out = list(argv)
    i = 0
    while i < len(out) - 1:
        if out[i] == "--rules" and out[i + 1].startswith("-") and not out[i + 1].startswith("--"):
            out[i:i + 2] = [f"--rules={out[i + 1]}"]
        i += 1
    return out


def main(argv=None) -> int:
    args = build_parser().parse_args(join_rules_value(sys.argv[1:] if argv is None else argv))
    shows = args.top_show + args.show
    init_output(verbosity=resolve_verbosity(args.top_verbose + args.verbose, args.top_quiet + args.quiet,
                                            env_var="CK3SM_VERBOSITY"),
                channels=resolve_channel_specs([f"{s.name}:{s.level}" for s in shows], env_var="CK3SM_SHOW"),
                channel_defs=CHANNELS, strict_channels=True)
    try:
        if getattr(args, "save", None):
            # a path, or the name of a save in the game's 'save games' folder (discover.find_save)
            args.save = str(find_save(args.save))
        return args.func(args)
    except (OutputExistsError, InPlaceError) as exc:     # before ValueError: InPlaceError is one
        say(ERROR, f"ERROR: {exc}", "io", err=True)
        return 2
    except (FileNotFoundError, SaveFormatError, ValueError) as exc:
        say(ERROR, f"ERROR: {exc}", "io", err=True)
        return 1
    except VerifyError as exc:
        say(ERROR, f"ERROR: verification failed, nothing written: {exc}", "io", err=True)
        return 3
