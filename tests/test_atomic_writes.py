"""Atomic writes of the config and the JSON reports (dazzle-filekit), Steam's Workshop folder in one place, and the
full channel list in --show's help.

The torn-write tests inject the failure inside dazzle-filekit's writer (its ``os.replace``, or a ``write`` that
stops half way), on a config in the test's own temporary config folder (conftest), so they cannot tear a real file.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from ck3_save_migrator import cli, config, discover
from ck3_save_migrator.lint import listed_workshop_mods
from tests.fixtures.make_ck3 import RULES_BODY, RULES_META, build_ck3

ROOT = Path(__file__).resolve().parents[1]
OLD = {"disabled": ["R21"], "trusted": {"mine": "a" * 64}}
NEW = {"disabled": ["R21", "R20"], "pack_dirs": ["D:/packs"], "trusted": {"mine": "b" * 64}}


@pytest.fixture
def ops():
    from dazzle_filekit import operations
    return operations


def test_a_rename_that_fails_leaves_the_old_config_whole(ops, monkeypatch):
    path = config.write_config(OLD)
    before = path.read_bytes()

    def no_replace(*a, **k):
        raise OSError("simulated: the disk filled up")
    monkeypatch.setattr(ops.os, "replace", no_replace)
    with pytest.raises(OSError, match="simulated"):
        config.write_config(NEW)
    assert path.read_bytes() == before
    assert config.disabled_ids() == ["R21"] and config.trusted_packs() == {"mine": "a" * 64}
    assert config.read_config()["disabled"] == ["R21"]           # the .tmp beside it, if left, is not read


def test_a_write_that_stops_half_way_leaves_the_old_config_whole(ops, monkeypatch):
    path = config.write_config(OLD)
    before = path.read_bytes()
    real_open = open

    class Torn:
        def __init__(self, f):
            self.f = f

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self.f.close()

        def write(self, text):
            self.f.write(text[: len(text) // 2])
            raise OSError("simulated: killed mid-write")

    monkeypatch.setattr(ops, "open", lambda *a, **k: Torn(real_open(*a, **k)), raising=False)
    with pytest.raises(OSError, match="killed mid-write"):
        config.write_config(NEW)
    assert path.read_bytes() == before
    assert config.read_config() == {"disabled": ["R21"], "trusted": {"mine": "a" * 64}}
    leftover = path.with_name(path.name + ".tmp")
    assert not leftover.exists() or leftover.read_bytes() != before          # tolerated: filekit leaves it


def test_the_atomic_write_writes_the_same_bytes_as_write_text(tmp_path):
    report = {"nickname": "the Tuatha Dé Danann", "name": "Áed", "rules": [{"id": "R23", "edited": 1}]}
    for indent in (2, 1):
        text = json.dumps(report, indent=indent, ensure_ascii=False)
        old, new = tmp_path / f"old{indent}.json", tmp_path / f"new{indent}.json"
        old.write_text(text, encoding="utf-8")
        config.atomic_write(new, text)
        assert new.read_bytes() == old.read_bytes() and "Dé".encode("utf-8") in new.read_bytes()


def test_migrates_report_and_lint_file_keep_their_bytes(tmp_path, capsys):
    src = tmp_path / "Áed_campaign.ck3"                  # a non-ASCII name: the report holds it as it is
    src.write_bytes(build_ck3(meta=RULES_META, body=RULES_BODY))
    out, rep = tmp_path / "o.ck3", tmp_path / "o.report.json"
    assert cli.main(["migrate", str(src), "--reference", "none", "-o", str(out), "--report", str(rep)]) == 0
    for p in (rep, out.with_suffix(".lint.json")):
        raw = p.read_bytes()
        assert raw == json.dumps(json.loads(raw), indent=2, ensure_ascii=False).encode("utf-8"), p.name
    assert "Áed".encode("utf-8") in rep.read_bytes()


def test_the_cli_does_not_import_dazzle_filekit_until_it_writes():
    r = subprocess.run([sys.executable, "-c", "import sys, ck3_save_migrator.cli; "
                        "print('dazzle_filekit' in sys.modules)"], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "False"


def test_the_workshop_folder_of_a_game_in_a_steam_library(tmp_path):
    lib = tmp_path / "SteamLibrary"
    game = lib / "steamapps" / "common" / "Crusader Kings III" / "game"
    game.mkdir(parents=True)
    content = lib / "steamapps" / "workshop" / "content" / "1158310"
    assert discover.workshop_content_dir(game) == content and discover.workshop_content_dir(None) is None
    (content / "111").mkdir(parents=True)
    meta = b'meta_data={\n\tmods={ "mod/ugc_111.mod" "mod/ugc_222.mod" "mod/local.mod" }\n}\n'
    assert listed_workshop_mods(meta, game) == ([content / "111"], ["222"])
    assert listed_workshop_mods(meta, None) == ([], [])


def test_shows_help_names_every_channel(capsys):
    with pytest.raises(SystemExit):
        cli.main(["migrate", "--help"])
    text = " ".join(capsys.readouterr().out.split())
    for ch in cli.CHANNELS:
        assert ch.name in text.split("(channels:", 1)[1], ch.name
    assert "gamediff" in text
