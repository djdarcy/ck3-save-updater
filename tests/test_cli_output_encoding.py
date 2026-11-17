"""Output never dies on a character the stream's encoding lacks (ck3_save_migrator/names.py, cli.main).

Measured 2026-11-17: a piped edit report holding "Shintō Way" ended with "'charmap' codec can't encode character".
"""

from __future__ import annotations

import io
import os
import subprocess
import sys
from pathlib import Path

import pytest

from ck3_save_migrator import names
from tests.fixtures.make_ck3 import build_ck3

REPO = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("text, want", [
    ("Ise Jingū", "Ise Jingu"), ("Ásatrú", "Asatru"), ("Jórvík", "Jorvik"), ("Toruń", "Torun"),
    ("Shafi'i", "Shafi'i"), ("伊勢", "伊勢"), ("Ælfweard", "Aelfweard"), ("Świętopełk", "Swietopelk"),
    ("Þórr", "Thorr"),
])
def test_fold_accents_takes_accents_off_and_keeps_the_rest(text, want):
    assert names.fold_accents(text) == want


def test_the_handler_writes_folded_letters_then_a_question_mark():
    assert "Ise Jingū 伊勢".encode("cp1252", names.FOLD_ERRORS) == b"Ise Jingu ??"


@pytest.mark.parametrize("errors", ["strict", "surrogateescape"])
def test_safe_output_makes_a_cp1252_stream_fold_instead_of_raising(errors):
    raw = io.BytesIO()
    s = io.TextIOWrapper(raw, encoding="cp1252", errors=errors)
    names.safe_output(s)
    s.write("faith 7 Shintō Way")
    s.flush()
    assert raw.getvalue() == b"faith 7 Shinto Way"


def test_a_stream_that_holds_every_character_writes_them_unchanged():
    raw = io.BytesIO()
    s = io.TextIOWrapper(raw, encoding="utf-8", errors="strict")
    names.safe_output(s)
    s.write("Shintō")
    s.flush()
    assert raw.getvalue() == "Shintō".encode("utf-8")


def test_a_piped_cp1252_edit_report_with_an_accented_name_does_not_crash(tmp_path):
    body = ('faiths={\n\tdatabase={\n\t\t7={\n\t\t\treligion=8\n\t\t\tholy_sites={ 0 1 }\n'
            '\t\t\teminent_holy_sites={ 0 }\n\t\t\tname="Shintō Way"\n\t\t}\n\t}\n}\n'
            'religion={\n\tholy_sites={\n\t\t0={\n\t\t\tholy_site_type=ise_jingu\n\t\t}\n'
            '\t\t1={\n\t\t\tholy_site_type=nara\n\t\t}\n\t}\n}\n').encode("utf-8")
    save = tmp_path / "Camp.ck3"
    save.write_bytes(build_ck3(body=body))
    env = dict(os.environ, PYTHONIOENCODING="cp1252")       # strict cp1252 on every platform, as a Windows pipe
    r = subprocess.run([sys.executable, "-m", "ck3_save_migrator", "edit", str(save), "set-eminent-holy-sites", "7",
                        "0 1", "--dry-run"], capture_output=True, cwd=REPO, env=env, timeout=120)
    assert r.returncode == 0, r.stderr.decode("cp1252", "replace")
    assert b"faith 7 Shinto Way" in r.stdout
