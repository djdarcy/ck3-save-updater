"""Run patches: a separate program run over the save, as it is.

The engine writes the current save with ``savefile.write_save`` (the same bytes ``migrate -o`` writes) to a temporary
``@@input@@``, runs the patch's ``command`` as its own process from the caller's working directory, reads
``@@output@@`` back with ``read_save``, and puts its gamestate in place. A non-zero exit, no output file, or a
command still running after ``run.timeout`` seconds (default 600, then it is stopped) fails closed: nothing of that
patch is applied, and the result carries the exit code and the last lines of stderr. The program's output goes to
files in the temporary folder, not into memory.

Variables in ``command`` (``@@name@@``): the ``RuleContext`` fields, ``python`` (the running interpreter),
``input``, ``output``, and the caller's own (``--var name=value``, ``--vars file.toml``). An element that is exactly
``"@@name@@"`` for a list variable becomes one argument per item. ``needs`` names variables the caller must give.

``tool = "<name>"`` with ``args = [...]`` stands for ``command = ["@@python@@", "<scripts folder>/<name>.py",
*args]``: the script in the tools add-on's scripts folder (``tool_script``), run by the same interpreter. It needs
no dazzlecmd-lib.
"""

from __future__ import annotations

import dataclasses
import subprocess
import sys
import tempfile
from pathlib import Path

from .. import savefile as sf
from .model import RUN_TIMEOUT, TEMPLATE, Patch, PatchError

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
    script = tool_script(patch, values) if patch.run.get("tool") else None    # refused before anything is written
    with tempfile.TemporaryDirectory(prefix="ck3sm-run-") as tmp:
        inp, outp = Path(tmp) / "input.ck3", Path(tmp) / "output.ck3"
        sf.write_save(_detached(save), inp)
        values.update(input=str(inp), output=str(outp))
        if script is not None:
            cmd = [sys.executable, str(script)] + expand(patch.run["args"], values, patch.source)
        else:
            cmd = expand(patch.run["command"], values, patch.source)
        timeout = patch.run.get("timeout", RUN_TIMEOUT)
        out_log, err_log = Path(tmp) / "stdout.txt", Path(tmp) / "stderr.txt"
        # the program's output goes to files, never into memory: a chatty program cannot exhaust it
        with out_log.open("wb") as so, err_log.open("wb") as se:
            try:
                code = subprocess.run(cmd, stdout=so, stderr=se, timeout=timeout).returncode
                why = f"exit code {code}" if code != 0 else None
            except subprocess.TimeoutExpired:
                code, why = None, f"it did not finish within {timeout:g} seconds (run.timeout) and was stopped"
        tail = _tail(err_log)
        if why is None and not outp.is_file():
            why = "no output file was written"
        if why is not None:
            return rule.result(extra={"failed": f"{patch.source}: the command failed ({why}); nothing applied",
                                      "exit_code": code, "stderr": tail})
        new = sf.read_save(outp)
    before = save.gamestate
    save.set_gamestate(new.gamestate)
    changed = new.gamestate != before
    return rule.result(matched=1, edited=int(changed), extra={"exit_code": 0, "stderr": tail})


def _tail(path: Path, lines: int = STDERR_LINES, window: int = 64 * 1024) -> list[str]:
    """The last ``lines`` lines of a log file, reading only its last ``window`` bytes."""
    with path.open("rb") as f:
        f.seek(0, 2)
        size = f.tell()
        f.seek(max(0, size - window))
        data = f.read()
    text = data.decode("utf-8", "replace").splitlines()
    if size > window and text:
        text = text[1:]                 # the first line read is probably cut
    return text[-lines:]


def tool_script(patch: Patch, values: dict) -> Path:
    """``<scripts folder>/<tool>.py`` for a ``tool =`` run patch. The folder: the ``scripts_dir`` variable, else the
    tools add-on's lookup (``CK3SM_SCRIPTS_DIR``, else the source checkout's ``tests/one-offs``)."""
    from .. import tools
    name = patch.run["tool"]
    folder = tools.scripts_dir(str(values["scripts_dir"]) if values.get("scripts_dir") else None)
    if folder is None:
        raise PatchError(f"{patch.source}: run.tool {name!r} needs a scripts folder, and none is set: give "
                         "--var scripts_dir=<folder> or set CK3SM_SCRIPTS_DIR")
    script = folder / f"{name}.py"
    if not script.is_file():
        raise PatchError(f"{patch.source}: run.tool {name!r}: no script {script} (the scripts folder is {folder})")
    return script.resolve()


def _detached(save):
    """A copy of ``save`` that is not tied to its input file, so writing it to a temporary path is never refused
    as writing over the input."""
    return dataclasses.replace(save, source=None, members=[dataclasses.replace(m) for m in save.members])
