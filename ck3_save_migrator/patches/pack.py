"""Turning a pack into ``Rule`` objects the migrator runs like its registered rules.

``rules_from_pack(pack)`` gives one ``Rule`` per patch, in the pack's ``order``, with the patch's id, name, since,
title (as the description), default and requires. A declarative patch's ``apply`` runs the engine; a code patch's
``apply`` IS the named function (so a pack that wraps the registered rules runs the very same code); a run patch's
runs its program. ``SHIPPED`` is the pack inside the package, read with ``importlib.resources``.
"""

from __future__ import annotations

import dataclasses
import hashlib
import importlib
import sys
import importlib.util
from importlib.resources import files
from pathlib import Path

from ..rule_types import Rule, RuleContext      # not from ..rules, whose REGISTRY is built by rules_from_pack
from . import engine
from .model import Pack, Patch, PatchError, as_folder, load_pack
from .run import context_values, run_patch

SHIPPED = "to_1_20"
CONTEXT_FIELDS = {f.name for f in dataclasses.fields(RuleContext) if f.name != "state"}


def shipped_pack_folder(name: str = SHIPPED):
    return files("ck3_save_migrator.packs").joinpath(name)


def read_pack(source=None) -> Pack:
    """The shipped pack when ``source`` is None; otherwise the pack folder at ``source`` (a path on disk)."""
    if source is None:
        return load_pack(shipped_pack_folder(), from_disk=False, context_fields=CONTEXT_FIELDS)
    folder = as_folder(source)
    if isinstance(folder, Path) and not folder.is_dir():
        raise PatchError(f"{folder}: not a pack folder")
    return load_pack(folder, from_disk=True, context_fields=CONTEXT_FIELDS)


def _function(patch: Patch):
    target, fn = patch.script.rsplit(":", 1)
    if target.endswith(".py"):
        folder = Path(str(patch.folder)).resolve()
        path = (folder / target).resolve()
        if not path.is_relative_to(folder):            # a link out of the folder; the loader refuses '..' already
            raise PatchError(f"{patch.source}: field 'script' names {target}, which is outside the patch folder")
        if not path.is_file():
            raise PatchError(f"{patch.source}: field 'script' names {target}, which is not in the patch folder")
        # registered under a unique name before it runs: dataclasses and the like look their module up there
        name = f"ck3sm_patch_{hashlib.sha256(str(path).encode()).hexdigest()[:16]}"
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        try:
            spec.loader.exec_module(mod)
        except Exception as exc:
            sys.modules.pop(name, None)
            raise PatchError(f"{patch.source}: field 'script': {target} failed to load "
                             f"({type(exc).__name__}: {exc})") from exc
    else:
        try:
            mod = importlib.import_module(target)
        except ImportError as exc:
            raise PatchError(f"{patch.source}: field 'script' names module {target!r}, which cannot be imported "
                             f"({exc})") from None
    func = getattr(mod, fn, None)
    if not callable(func):
        raise PatchError(f"{patch.source}: field 'script' names {fn!r}, which {target!r} does not define")
    return func


def _declarative(patch: Patch):
    def apply(save, ctx, rule):
        pl = engine.apply_patch(save, patch, context_values(ctx))
        extra = {"edits": pl.stats}
        if pl.failure:
            extra["failed"] = pl.failure
        count = {"found": "found", "blocks": "blocks", "blocks-hit": "blocks_hit"}[patch.matched]
        return rule.result(matched=sum(r.get(count, 0) for r in pl.stats),
                           edited=len(pl.edits) if not pl.failure else 0,
                           extra=extra)
    apply.patch = patch
    apply.__doc__ = f"{patch.title} (the declarative patch {patch.source}: {len(patch.edits)} edit(s))"
    return apply


def _runner(patch: Patch):
    def apply(save, ctx, rule):
        return run_patch(save, patch, ctx, rule, ctx.state.get("patch_vars", {}))
    apply.patch = patch
    apply.__doc__ = f"{patch.title} (the run patch {patch.source})"
    return apply


def rules_from_pack(source=None, *, allow_run: bool = False) -> list[Rule]:
    """One ``Rule`` per patch of a pack, in its order. A pack read from a folder whose patches run code (a script or
    run patch) is refused unless ``allow_run``: that code runs with the player's permissions. The check covers the
    whole pack before any of its code is imported."""
    pack = source if isinstance(source, Pack) else read_pack(source)
    if pack.from_disk and not allow_run:
        for p in pack.ordered():
            if p.kind == "script":
                raise PatchError(f"{p.source}: a script patch runs Python code from the pack folder with your "
                                 "permissions; pass --allow-run to let it")
            if p.kind == "run":
                raise PatchError(f"{p.source}: a run patch runs a program with your permissions; pass --allow-run "
                                 "to let it")
    rules = []
    for p in pack.ordered():
        if p.kind == "script":
            apply = _function(p)
        elif p.kind == "run":
            apply = _runner(p)
        else:
            apply = _declarative(p)
        rules.append(Rule(p.id, p.name, p.since, p.title, apply, default=p.default, requires=p.requires))
    return rules


def verdict(save_gamestate: bytes, patch: Patch, ctx: RuleContext | None = None) -> tuple[str, str]:
    """(verdict, detail) for ``patch`` on a gamestate, which is only read: "needed" (some edit would edit; the
    detail counts the edits), "done" (none would), "fails" (an ``expect`` or ``need_path`` does not hold; the
    detail names the edit, the path and the count), or "unknown" (a code or run patch: only running it would tell,
    and checking runs nothing)."""
    if patch.kind != "declarative":
        return "unknown", f"a {'code' if patch.kind == 'script' else 'run'} patch: only running it would tell"
    pl = engine.plan(save_gamestate, patch, context_values(ctx or RuleContext()))
    if pl.failure:
        return "fails", pl.failure
    if pl.needed:
        return "needed", f"{len(pl.edits)} edit(s)"
    return "done", "nothing to edit" + (" (its done marker is present)" if pl.done else "")


def status(save_gamestate: bytes, patch: Patch, ctx: RuleContext | None = None) -> str:
    """"needed", "done", "fails" or "unknown" (code and run patches run when selected); see ``verdict``."""
    return verdict(save_gamestate, patch, ctx)[0]
