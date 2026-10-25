"""Command-line entry point for ck3-save-migrator (the `ck3-save-migrator` command).

Exit codes: 0 ok, 1 bad input, 2 refused by a guard (output exists, in-place), 3 verification failed.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from pathlib import Path

from ._version import __app_name__, get_display_version
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


def eprint(*a) -> None:
    print(*a, file=sys.stderr)


def cmd_inspect(args) -> int:
    save = read_save(args.save)
    h = save.header
    newline = "CRLF" if h.newline == b"\r\n" else "LF"   # outside the f-string: 3.10/3.11 forbid backslashes there
    print(f"file      : {save.source}")
    print(f"header    : {h.raw.rstrip().decode('ascii')}  (kind {h.kind:02x} {save.kind_name}, "
          f"meta length {h.meta_len:,}, newline {newline})")
    print(f"meta block: {len(save.meta):,} bytes")
    for m in save.members:
        print(f"member    : {m.name}  {len(m.data):,} bytes inflated")
    for w in save.warnings:
        print(f"WARNING   : {w}")
    return 0


GAME_DIR_CANDIDATES = (
    r"E:\SteamLibrary\steamapps\common\Crusader Kings III\game",
    r"C:\Program Files (x86)\Steam\steamapps\common\Crusader Kings III\game",
    "~/.steam/steam/steamapps/common/Crusader Kings III/game",
    "~/Library/Application Support/Steam/steamapps/common/Crusader Kings III/game",
)


def find_game_dir(explicit: str | None) -> Path | None:
    """--game-dir, else $CK3_GAME_DIR, else the usual Steam locations."""
    for cand in (explicit, os.environ.get("CK3_GAME_DIR"), *GAME_DIR_CANDIDATES):
        if cand and (Path(cand).expanduser() / "common" / "landed_titles").is_dir():
            return Path(cand).expanduser()
    return None


DEV_REFERENCE = Path("private/data/originals/reference-1.20/ref_1_20_987_10_27.ck3")


def find_reference(explicit: str | None) -> Path | None:
    """--reference, else $CK3_REFERENCE_SAVE, else this project's 987 reference save when run from the repo.

    ``--reference none`` means no reference (R8-R12 skip), whatever the environment holds.
    """
    if explicit is not None and explicit.lower() == "none":
        return None
    for cand in (explicit, os.environ.get("CK3_REFERENCE_SAVE"), str(DEV_REFERENCE)):
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


def _emit(args, save, results, out: Path, report_path: str | None, ctx, in_sha: str) -> None:
    result = write_save(save, out, force=args.force, recompress=args.recompress, dry_run=args.dry_run)
    tag = "[dry-run] would write" if result.dry_run else "wrote"
    how = "input bytes reused verbatim" if result.verbatim else "re-deflated"
    print(f"{tag}: {out}")
    print(f"  rules applied : {len(results)}" + (f"  (wos shape: {ctx.wos_shape})" if any(r.id == 'R10' for r in results) else ""))
    for r in results:
        note = f"  ({r.extra['skipped']})" if "skipped" in r.extra else ""
        print(f"    {r.id:3} {r.name:22} matched {r.matched:>8,}  edited {r.edited:>8,}{note}")
    print(f"  size          : {result.size:,} bytes ({how})")
    print(f"  meta length   : {result.meta_len:,}")
    print(f"  sha256        : {result.sha256}")
    print(f"  gamestate sha : {result.gamestate_sha256}")
    print("  verified      : re-read, meta copies equal, length field correct")
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
        }
        Path(report_path).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"  report        : {report_path}")


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
    save = read_save(args.save)
    for w in save.warnings:
        eprint(f"WARNING: {w}")
    # one output per custom-faith shape only when there is a custom faith to shape; otherwise one plain output
    branch = may_branch and bool(custom_faith_names(save.gamestate))
    _check_paths(args, outputs(branch), existence=True)        # before any rule runs
    in_sha = sha256(save.to_bytes())
    ctx = RuleContext(game_dir=find_game_dir(args.game_dir), portraits_version=args.portraits_version,
                      reference=reference, wos_shape=shapes[0])
    if not branch:
        _emit(args, save, run_rules(save, rules, ctx), out, args.report, ctx, in_sha)
        return 0
    # both shapes: run the shared rules once, branch at R10
    shared = run_rules(save, rules[:split], ctx)
    for shape in shapes:
        s2 = copy.deepcopy(save)
        c2 = copy.copy(ctx)
        c2.state = copy.deepcopy(ctx.state)
        c2.wos_shape = shape
        results = shared + run_rules(s2, rules[split:], c2)
        _emit(args, s2, results, branch_path(out, shape),
              str(branch_path(Path(args.report), shape)) if args.report else None, c2, in_sha)
    return 0


def cmd_rules(args) -> int:
    for r in REGISTRY:
        flag = "" if r.default else "  (opt-in)"
        print(f"{r.id:3} {r.name:22} since {r.since:28} {r.description}{flag}")
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
    p.set_defaults(func=cmd_migrate)

    p = sub.add_parser("rules", help="list the migration rules")
    p.set_defaults(func=cmd_rules)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (OutputExistsError, InPlaceError) as exc:     # before ValueError: InPlaceError is one
        eprint(f"ERROR: {exc}")
        return 2
    except (FileNotFoundError, SaveFormatError, ValueError) as exc:
        eprint(f"ERROR: {exc}")
        return 1
    except VerifyError as exc:
        eprint(f"ERROR: verification failed, nothing written: {exc}")
        return 3
