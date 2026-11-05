"""The core never needs dazzlecmd-lib: with any import of it made to fail, the package imports, builds the rules from
the shipped pack, migrates a synthetic save through the command line, and shows the help of the optional ``tools``
command."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from tests.fixtures.make_ck3 import RULES_BODY, RULES_META, build_ck3

ROOT = Path(__file__).resolve().parents[1]

PROBE = """
import sys
sys.modules["dazzlecmd_lib"] = None              # any import of it now fails
import ck3_save_migrator
from ck3_save_migrator.patches import rules_from_pack
assert len(rules_from_pack()) == 27
from ck3_save_migrator import cli
code = cli.main(["migrate", sys.argv[1], "--no-lint", "-o", sys.argv[2], "-q"])
assert code == 0, code
assert "dazzlecmd_lib" not in [m for m, v in sys.modules.items() if v is not None]
try:
    cli.main(["tools", "--help"])
except SystemExit as exc:
    assert exc.code == 0, exc.code
else:
    raise AssertionError("tools --help did not exit")
print("ok")
"""


def test_the_core_runs_with_dazzlecmd_lib_unimportable(tmp_path):
    src = tmp_path / "My_Old_Campaign.ck3"
    src.write_bytes(build_ck3(meta=RULES_META, body=RULES_BODY))
    out = tmp_path / "out.ck3"
    env = {"CK3_GAME_DIR": "none", "CK3_REFERENCE_SAVE": "none", "PATH": ""}
    r = subprocess.run([sys.executable, "-c", PROBE, str(src), str(out)], cwd=ROOT, capture_output=True, text=True,
                       env={**__import__("os").environ, **env})
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip().endswith("ok") and out.is_file()
