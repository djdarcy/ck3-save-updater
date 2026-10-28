"""Run patches: a separate program run over the save, as it is.

The engine writes the current save with ``savefile.write_save`` (the same bytes ``migrate -o`` writes) to a temporary
``@@input@@``, runs the patch's ``command`` as its own process from the caller's working directory, reads
``@@output@@`` back with ``read_save``, and puts its gamestate in place. A non-zero exit, or no output file, fails
closed: nothing of that patch is applied, and the result carries the exit code and the last lines of stderr.

Variables in ``command`` (``@@name@@``): the ``RuleContext`` fields, ``python`` (the running interpreter),
``input``, ``output``, and the caller's own (``--var name=value``, ``--vars file.toml``). An element that is exactly
``"@@name@@"`` for a list variable becomes one argument per item. ``needs`` names variables the caller must give.
"""

from __future__ import annotations

import dataclasses
import subprocess
import sys
import tempfile
from pathlib import Path

from .. import savefile as sf
from .model import TEMPLATE, Patch, PatchError

STDERR_LINES = 20


def context_values(ctx) -> dict:
    """The ``RuleContext`` fields as template values (``state`` excepted)."""
    return {f.name: getattr(ctx, f.name) for f in dataclasses.fields(ctx) if f.name != "state"}


def expand(command, values: dict, where: str) -> list[str]:
    """``command`` with every ``@@name@@`` filled; a whole-element list variable becomes several arguments."""
    out: list[str] = []
    for part in command:
        whole = TEMPLATE.fullmatch(part)
        if whole and isinstance(values.get(whole.group(1)), (list, tuple)):
            out += [str(x) for x in values[whole.group(1)]]
            continue

        def sub(m):
            name = m.group(1)
            if name not in values or values[name] is None:
                raise PatchError(f"{where}: run.command uses @@{name}@@, which has no value (give it with "
                                 f"--var {name}=...)")
            v = values[name]
            if isinstance(v, (list, tuple)):
                raise PatchError(f"{where}: @@{name}@@ is a list; write it as a whole element, \"@@{name}@@\"")
            return str(v)
        out.append(TEMPLATE.sub(sub, part))
    return out


def run_patch(save, patch: Patch, ctx, rule, user_vars: dict):
    """Apply a run patch to ``save`` (a ``CK3Save``); returns the rule result."""
    values = {**context_values(ctx), **user_vars, "python": sys.executable}
    missing = [n for n in patch.run["needs"] if values.get(n) in (None, "")]
    if missing:
        raise PatchError(f"{patch.source}: run.needs {', '.join(missing)}, which the caller did not give "
                         f"(--var {missing[0]}=... or --vars <file.toml>)")
    with tempfile.TemporaryDirectory(prefix="ck3sm-run-") as tmp:
        inp, outp = Path(tmp) / "input.ck3", Path(tmp) / "output.ck3"
        sf.write_save(_detached(save), inp)
        values.update(input=str(inp), output=str(outp))
        cmd = expand(patch.run["command"], values, patch.source)
        proc = subprocess.run(cmd, capture_output=True)
        tail = proc.stderr.decode("utf-8", "replace").splitlines()[-STDERR_LINES:]
        if proc.returncode != 0 or not outp.is_file():
            why = (f"exit code {proc.returncode}" if proc.returncode != 0 else "no output file was written")
            return rule.result(extra={"failed": f"{patch.source}: the command failed ({why}); nothing applied",
                                      "exit_code": proc.returncode, "stderr": tail})
        new = sf.read_save(outp)
    before = save.gamestate
    save.set_gamestate(new.gamestate)
    changed = new.gamestate != before
    return rule.result(matched=1, edited=int(changed), extra={"exit_code": 0, "stderr": tail})


def _detached(save):
    """A copy of ``save`` that is not tied to its input file, so writing it to a temporary path is never refused
    as writing over the input."""
    return dataclasses.replace(save, source=None, members=[dataclasses.replace(m) for m in save.members])
