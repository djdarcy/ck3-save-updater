"""The CLI's narration through dazzle-loglib: default output unchanged, -q leaves results, -v adds detail.

The golden file was recorded from the CLI BEFORE it moved to loglib (print-based), so the first test proves the
move changed nothing a user sees at the default verbosity. Regenerate it only on purpose:
CK3SM_REGEN_GOLDEN=1 python -m pytest tests/test_cli_output.py
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest

from ck3_save_migrator import cli
from tests.fixtures.make_ck3 import build_ck3
from tests.fixtures.religion import OLD_BODY, OLD_META, REF_BODY, REF_META

GOLDEN = Path(__file__).parent / "fixtures" / "cli_golden.json"


@pytest.fixture
def saves(tmp_path):
    old, ref = tmp_path / "old.ck3", tmp_path / "ref.ck3"
    old.write_bytes(build_ck3(meta=OLD_META, body=OLD_BODY))
    ref.write_bytes(build_ck3(meta=REF_META, body=REF_BODY))
    return tmp_path, old, ref


def commands(tmp: Path, old: Path, ref: Path) -> dict[str, list[str]]:
    return {
        "inspect": ["inspect", str(old)],
        "rules": ["rules"],
        "lint": ["lint", str(old), "--no-keys", "--reference", "none"],
        "migrate": ["migrate", str(old), "--rules", "all", "--reference", str(ref), "--wos-shape", "faith",
                    "-o", str(tmp / "out.ck3"), "--report", str(tmp / "r.json"), "--no-lint"],
    }


def run(argv: list[str], capsys, tmp: Path) -> tuple[int, str, str]:
    code = cli.main(argv)
    cap = capsys.readouterr()
    norm = lambda s: s.replace(str(tmp), "<TMP>").replace("\\", "/")
    return code, norm(cap.out), norm(cap.err)


def test_default_output_is_unchanged(saves, capsys):
    tmp, old, ref = saves
    got = {name: run(argv, capsys, tmp)[1] for name, argv in commands(tmp, old, ref).items()}
    if os.environ.get("CK3SM_REGEN_GOLDEN") == "1":
        GOLDEN.write_text(json.dumps(got, indent=1), encoding="utf-8")
        pytest.skip("golden regenerated")
    assert got == json.loads(GOLDEN.read_text(encoding="utf-8"))


def test_quiet_leaves_the_results(saves, capsys):
    tmp, old, ref = saves
    argv = commands(tmp, old, ref)["migrate"] + ["--force", "-q"]
    code, out, err = run(argv, capsys, tmp)
    assert code == 0
    assert "wrote: <TMP>/out.ck3" in out               # the result
    assert "rules applied" not in out and "sha256" not in out    # the narration
    code, out, _ = run(["lint", str(old), "--no-keys", "--reference", "none", "-qqq"], capsys, tmp)
    assert out == ""                                     # errors only: a clean save says nothing


def test_verbose_adds_timing_and_io(saves, capsys):
    tmp, old, ref = saves
    argv = commands(tmp, old, ref)["migrate"] + ["--force", "-vv"]
    code, out, err = run(argv, capsys, tmp)
    assert code == 0
    assert re.search(r"R1 +[\w-]+ +\d+\.\d+s", err)       # timing, +1, stderr
    assert "read <TMP>/old.ck3" in err                   # io, +2, stderr
    assert "rules applied" in out                        # the default narration is still there


def test_verbosity_flags_work_before_and_after_the_sub_command():
    parse = cli.build_parser().parse_args
    for argv, want in ((["-v", "rules"], 1), (["rules", "-v"], 1), (["-v", "rules", "-v"], 2), (["-q", "rules"], -1)):
        a = parse(argv)
        assert (a.top_verbose + a.verbose) - (a.top_quiet + a.quiet) == want, argv


def test_every_emitted_channel_is_declared():
    src = Path(cli.__file__).read_text(encoding="utf-8")
    used = set(re.findall(r'channel="(\w+)"', src)) | set(re.findall(r"say\([^)]*?, \"(\w+)\"", src))
    declared = {c.name for c in cli.CHANNELS}
    assert used and used <= declared, used - declared
