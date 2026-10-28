"""spike_flat_scripts: can a dazzlecmd-lib aggregator run the project's old one-off scripts EXACTLY as they are --
a flat folder of .py files with no manifests, run as their own process -- by generating a shadow kit (one manifest per
script, in a temp folder, `pass_through: true`, `script_path` = the script's absolute path)? Epic #14, 2026-10-27,
after djdarcy: "all our old tools we use to build our save can still be used exactly as they are with our pypi tool".

Prediction: yes on 0.8.55 and 0.10.x (registry.make_subprocess_runner runs [python, script] + argv, cwd = caller's;
os.path.join(tool_dir, <absolute>) keeps the absolute path).
Known answer: section_head.py run with no arguments prints its usage and exits non-zero, the same as running it
directly; run with a real argument list it matches the direct run's stdout byte for byte (checked on a tiny synthetic
gamestate written to a temp file).
Control (designed to fail): a shadow manifest whose script_path names a file that does not exist must not exit 0.
The scripts folder is only read; the check at the end proves no file in it changed (mtimes and sizes).

Usage: <python with dazzlecmd-lib> -I tests/one-offs/spike_flat_scripts.py
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent


def snapshot(folder: Path):
    return {p.name: (p.stat().st_size, p.stat().st_mtime_ns) for p in folder.glob("*.py")}


def shadow_kit(root: Path, scripts: dict[str, Path], manifest=".ckt.json"):
    (root / "kits").mkdir(parents=True)
    (root / "kits" / "oneoffs.kit.json").write_text(json.dumps({
        "name": "oneoffs", "version": "0.0.0", "always_active": True, "tools_dir": "tools", "manifest": manifest,
        "tools": [f"oneoffs:{n}" for n in scripts]}), encoding="utf-8")
    for name, path in scripts.items():
        d = root / "tools" / "oneoffs" / name
        d.mkdir(parents=True)
        (d / manifest).write_text(json.dumps({
            "name": name, "namespace": "oneoffs", "version": "0.0.0", "description": f"(one-off) {path.name}",
            "pass_through": True, "runtime": {"type": "python", "script_path": str(path)}}), encoding="utf-8")


def via_engine(root: Path, cfg: Path, argv):
    from dazzlecmd_lib import AggregatorEngine
    engine = AggregatorEngine(name="ckt", command="ckt", tools_dir="tools", kits_dir="kits", manifest=".ckt.json",
                              config_dir=str(cfg), project_root=str(root))
    try:
        return engine.run(argv)
    except SystemExit as e:
        return e.code


def main():
    import dazzlecmd_lib
    print("dazzlecmd-lib", getattr(dazzlecmd_lib, "__version__", "?"))
    before = snapshot(HERE)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        gs = tmp / "tiny_gamestate"
        gs.write_bytes(b"meta_data={\n\tversion=\"1.8.1\"\n}\nplayed_character={\n\tcharacter=16835700\n}\n")
        shadow_kit(tmp / "shadow", {"section_head": HERE / "section_head.py", "missing": HERE / "no_such_script.py"})
        cases = [("no args", ["section_head"], []),
                 ("real args", ["section_head", str(gs), "meta_data"], [str(gs), "meta_data"])]
        for label, argv, direct_args in cases:
            direct = subprocess.run([sys.executable, str(HERE / "section_head.py"), *direct_args],
                                    capture_output=True, cwd=tmp)
            # the engine's subprocess inherits our stdout: capture it at the file-descriptor level via a child run
            child = subprocess.run([sys.executable, "-I", "-c",
                                    "import sys, json; sys.path.insert(0, %r); import spike_flat_scripts as s; "
                                    "from pathlib import Path; sys.exit(s.via_engine(Path(%r), Path(%r), json.loads(%r)))"
                                    % (str(HERE), str(tmp / "shadow"), str(tmp / "cfg"), json.dumps(argv))],
                                   capture_output=True, cwd=tmp)
            same = child.stdout == direct.stdout
            print(f"{label:10} direct rc={direct.returncode} engine rc={child.returncode} stdout identical={same} "
                  f"({len(direct.stdout)} bytes)")
        rc = subprocess.run([sys.executable, "-I", "-c",
                             "import sys, json; sys.path.insert(0, %r); import spike_flat_scripts as s; "
                             "from pathlib import Path; sys.exit(s.via_engine(Path(%r), Path(%r), ['missing']))"
                             % (str(HERE), str(tmp / "shadow"), str(tmp / "cfg"))],
                            capture_output=True, cwd=tmp)
        print(f"control    missing script rc={rc.returncode} said={rc.stderr.decode(errors='replace').strip()[-90:]}")
    print("scripts folder unchanged:", snapshot(HERE) == before)


if __name__ == "__main__":
    main()
