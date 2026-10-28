"""spike_module_tool: does a dazzlecmd-lib aggregator dispatch a tool named by MODULE (not by script file), with the
kit and manifest read from a folder that stands in for the installed package (site-packages), on the PyPI release
(0.8.55) as well as the local 0.10.x? Bears on the standalone-tools aggregator design (epic #14, 2026-10-27).

Prediction: yes on both (registry.py reads runtime.module and imports it).
Control (designed to fail): a manifest naming a module that does not exist must NOT exit 0.
Known answer: the tool prints "ran ['x1']" when dispatched as `ckt demo x1`.

Usage: <python with dazzlecmd-lib> -I tests/one-offs/spike_module_tool.py
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
from pathlib import Path


def write(p: Path, text: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def main():
    import dazzlecmd_lib
    from dazzlecmd_lib import AggregatorEngine
    print("dazzlecmd-lib", getattr(dazzlecmd_lib, "__version__", "?"))
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        site = tmp / "site"                                   # stands in for site-packages
        write(site / "ckt_demo_tool.py", "def main(argv=None):\n    print('ran', argv)\n    return 0\n")
        root = site / "ckt_pkg"                               # the installed package's own folder
        write(root / "kits" / "core.kit.json", json.dumps({
            "name": "core", "version": "0.1.0", "always_active": True, "tools_dir": "tools",
            "manifest": ".ckt.json", "tools": ["core:demo", "core:modonly", "core:broken"]}))
        # demo: module + a script_path (the runner acts only when script_path is set; the file need not exist)
        # modonly: module alone (found 2026-10-27: exits 1 silently on both lib versions)
        # broken: the control, a module that does not exist
        for name, module, script in (("demo", "ckt_demo_tool", "tool.py"), ("modonly", "ckt_demo_tool", None),
                                     ("broken", "ckt_no_such_module", "tool.py")):
            runtime = {"type": "python", "module": module, "entry_point": "main"}
            if script:
                runtime["script_path"] = script
            write(root / "tools" / "core" / name / ".ckt.json", json.dumps({
                "name": name, "namespace": "core", "version": "0.1.0", "description": f"{name} tool",
                "runtime": runtime}))
        sys.path.insert(0, str(site))
        cwd = os.getcwd()
        os.chdir(tmp)                                         # an unrelated working directory
        try:
            for argv in (["demo", "x1"], ["modonly", "x1"], ["broken"]):
                out, err = io.StringIO(), io.StringIO()
                engine = AggregatorEngine(name="ckt", command="ckt", tools_dir="tools", kits_dir="kits",
                                          manifest=".ckt.json", config_dir=str(tmp / "cfg"), project_root=str(root))
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    try:
                        rc = engine.run(argv)
                    except SystemExit as e:
                        rc = e.code
                    except Exception as e:                     # noqa: BLE001 -- a spike reports
                        rc = f"raised {type(e).__name__}: {e}"
                last = (out.getvalue() + err.getvalue()).strip().splitlines()[-1:] or ["-"]
                print(f"{' '.join(argv):10} rc={rc}  said={last[0][:110]}")
        finally:
            os.chdir(cwd)


if __name__ == "__main__":
    main()
