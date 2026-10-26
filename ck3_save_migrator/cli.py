"""Command-line entry point for ck3-save-migrator (the `ck3-save-migrator` command).

Exit codes: 0 ok, 1 bad input, 2 refused by a guard (output exists, in-place), 3 verification failed,
4 lint found an error (migrate: the output is still written, for inspection).
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import time
from pathlib import Path

from dazzle_loglib import (
    DEFAULT, DIAGNOSTICS, ERROR, EXTRA, MINIMAL, WARNING,
    ChannelDef, get_output, init_output, parse_channel_spec, resolve_channel_specs, resolve_verbosity,
)

from ._version import __app_name__, get_display_version
from .lint import listed_workshop_mods, lint_gamestate, load_game_data
from .rules import REGISTRY, RuleContext, run_rules, select
from .rules.religion_1_20 import custom_faith_names
from .savefile import (
    InPlaceError,
    OutputExistsError,
    SaveFormatError,
    VerifyError,
    default_output,
    read_save,
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
    for w in save.warnings:
        say(MINIMAL, f"WARNING   : {w}", "io")
    return 0


GAME_DIR_CANDIDATES = (
    r"E:\SteamLibrary\steamapps\common\Crusader Kings III\game",
    r"C:\Program Files (x86)\Steam\steamapps\common\Crusader Kings III\game",
    "~/.steam/steam/steamapps/common/Crusader Kings III/game",
    "~/Library/Application Support/Steam/steamapps/common/Crusader Kings III/game",
)


def find_game_dir(explicit: str | None) -> Path | None:
    """--game-dir, else $CK3_GAME_DIR, else the usual Steam locations. ``none`` (flag or variable) means no game
    folder: the rules and checks that need one skip."""
    env = os.environ.get("CK3_GAME_DIR")
    given, source = (explicit, "--game-dir") if explicit is not None else (env, "CK3_GAME_DIR")
    if given:
        if given.lower() == "none":
            return None
        p = Path(given).expanduser()
        if (p / "common" / "landed_titles").is_dir():
            return p
        # a folder that was named but is not a game folder is refused, never swapped for a discovered one
        raise FileNotFoundError(f"{source} {given} is not the game's 'game' folder "
                                f"(expected {p / 'common' / 'landed_titles'})")
    for cand in GAME_DIR_CANDIDATES:
        if cand and (Path(cand).expanduser() / "common" / "landed_titles").is_dir():
            return Path(cand).expanduser()
    return None


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
        if out.resolve() == src:
            raise InPlaceError(f"refusing to write over the input file: {out}")
        folders = ([] if args.dry_run else [out.parent]) + ([Path(report).parent] if report else [])
        for folder in folders:
            if not (folder if str(folder) else Path(".")).is_dir():
                raise FileNotFoundError(f"output folder does not exist: {folder}")
        if existence and out.exists() and not args.force and not args.dry_run:
            raise OutputExistsError(f"output already exists: {out} (use --force to overwrite)")


def cmd_migrate(args) -> int:
    out = Path(args.output) if args.output else default_output(args.save)
    rules = select(args.rules, include_off=("R7",) if args.bump_version else ())
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
    in_sha = sha256(save.to_bytes())
    ctx = RuleContext(game_dir=find_game_dir(args.game_dir), portraits_version=args.portraits_version,
                      reference=reference, wos_shape=shapes[0],
                      old_game_dir=Path(args.old_game_dir) if args.old_game_dir else None,
                      expansion_orders=not args.no_expansion_orders)
    known = None          # what the game and the mods define: read once, shared by both outputs
    lint_errors = 0

    def lint_of(s):
        nonlocal known, lint_errors
        if args.no_lint:
            return None
        if known is None:
            ref_g = read_save(reference).gamestate if reference else None
            mods, missing = listed_workshop_mods(save.meta, ctx.game_dir) if args.lint_mods == "save" else ([], [])
            known = load_game_data(ctx.game_dir, ref_g, mods, mods_missing=missing,
                                   reference_name=str(reference) if reference else None)
        rep = lint_gamestate(s.gamestate, known=known)
        lint_errors += rep.errors
        return rep

    if not branch:
        results = run_rules_timed(save, rules, ctx)
        _emit(args, save, results, out, args.report, ctx, in_sha, lint_of(save))
    else:
        # both shapes: run the shared rules once, branch at R10
        shared = run_rules_timed(save, rules[:split], ctx)
        for shape in shapes:
            s2 = copy.deepcopy(save)
            c2 = copy.copy(ctx)
            c2.state = copy.deepcopy(ctx.state)
            c2.wos_shape = shape
            results = shared + run_rules_timed(s2, rules[split:], c2)
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
        return lint_gamestate(save.gamestate, keys=False)
    reference = read_save(reference_path).gamestate if reference_path else None
    mods, missing = listed_workshop_mods(save.meta, game_dir) if getattr(args, "mods", "save") == "save" else ([], [])
    data = load_game_data(game_dir, reference, mods, mods_missing=missing,
                          reference_name=str(reference_path) if reference_path else None)
    return lint_gamestate(save.gamestate, known=data)


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


def cmd_rules(args) -> int:
    for r in REGISTRY:
        flag = "" if r.default else "  (opt-in)"
        say(MINIMAL, f"{r.id:3} {r.name:22} since {r.since:28} {r.description}{flag}", "rules")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=__app_name__, description="Migrate old Crusader Kings III saves forward to the current game version: inspect, patch, and revive .ck3 save files")
    parser.add_argument("--version", action="version", version=f"{__app_name__} {get_display_version()}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("inspect", help="show a save's header, meta block and zip members")
    p.add_argument("save")
    p.set_defaults(func=cmd_inspect)

    p = sub.add_parser("migrate", help="read a save and write a migrated copy (never in place)")
    p.add_argument("save")
    p.add_argument("-o", "--output", help="output path (default: <name>.migrated.ck3 beside the input)")
    p.add_argument("--dry-run", action="store_true", help="build and verify in memory; write nothing")
    p.add_argument("--force", action="store_true", help="overwrite an existing output file")
    p.add_argument("--recompress", action="store_true",
                   help="re-deflate the zip even when nothing changed (default reuses the input bytes)")
    p.add_argument("--rules", help="'all' or a comma list of rule ids/names (e.g. R1,title-names); default none")
    p.add_argument("--report", help="write a JSON report of the rules' counts to this path")
    p.add_argument("--bump-version", action="store_true",
                   help="kept for compatibility: R7 (version bump) is now part of --rules all")
    p.add_argument("--portraits-version", type=int, help="R7 also sets portraits_version to this")
    p.add_argument("--reference", help="a save written by the target game version, for R8-R12 "
                   "(default: $CK3_REFERENCE_SAVE, else the project's 987 reference)")
    p.add_argument("--wos-shape", choices=("faith", "rite", "both"), default="both",
                   help="R10: custom faiths as their own faith, as a rite of their template's faith, "
                        "or both (default: two outputs, <stem>__wos-faith / __wos-rite, when a reference is "
                        "given; a save without custom faiths yields one output)")
    p.add_argument("--game-dir", help="the game's 'game' folder (default: $CK3_GAME_DIR or the usual Steam paths)")
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
    p.set_defaults(func=cmd_migrate)

    p = sub.add_parser("lint", help="check a 1.20-layout save before loading it: structure, cross-references, "
                                    "unknown keys (exit 4 when an error is found)")
    p.add_argument("save")
    p.add_argument("--reference", help="a save written by the target game version, for the key-name check "
                   "(default: $CK3_REFERENCE_SAVE, else the project's 987 reference; 'none' to skip)")
    p.add_argument("--game-dir", help="the game's 'game' folder (default: $CK3_GAME_DIR or the usual Steam paths)")
    p.add_argument("--no-keys", action="store_true",
                   help="skip the checks that need game data: key names and what 1.20 will log")
    p.add_argument("--mods", choices=("save", "none"), default="save",
                   help="which mods to assume active when the save loads: the Workshop mods the save lists "
                        "(default; those installed), or none (a vanilla load)")
    p.add_argument("--json", help="write the findings to this JSON file")
    p.set_defaults(func=cmd_lint)

    p = sub.add_parser("rules", help="list the migration rules")
    p.set_defaults(func=cmd_rules)
    # the verbosity flags before and after the sub-command, one chain (see add_verbosity_flags)
    add_verbosity_flags(parser, top=True)
    for sp in sub.choices.values():
        add_verbosity_flags(sp)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    shows = args.top_show + args.show
    init_output(verbosity=resolve_verbosity(args.top_verbose + args.verbose, args.top_quiet + args.quiet,
                                            env_var="CK3SM_VERBOSITY"),
                channels=resolve_channel_specs([f"{s.name}:{s.level}" for s in shows], env_var="CK3SM_SHOW"),
                channel_defs=CHANNELS, strict_channels=True)
    try:
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
