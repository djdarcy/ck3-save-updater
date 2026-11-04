"""docs_guard (tests/one-offs/docs_guard.py): the Documents guard used around game runs for #40.

Every test builds its own Documents folder and backups folder under tmp_path and passes both explicitly, so a broken
guard can never reach the real Documents folder (the guard's default path is never used here).
"""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

GUARD_PATH = Path(__file__).resolve().parent / "one-offs" / "docs_guard.py"


@pytest.fixture(scope="module")
def guard():
    spec = importlib.util.spec_from_file_location("docs_guard_probe", GUARD_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    try:
        spec.loader.exec_module(mod)
        yield mod
    finally:
        sys.modules.pop(spec.name, None)


@pytest.fixture
def docs(tmp_path):
    d = tmp_path / "Crusader Kings III"
    (d / "save games").mkdir(parents=True)
    (d / "mod").mkdir()
    (d / "logs").mkdir()
    (d / "dlc_load.json").write_text(json.dumps({"enabled_mods": ["mod/a.mod"], "disabled_dlcs": []}))
    (d / "pdx_settings.txt").write_text("settings = { x = 1 }\n")
    (d / "mod" / "a.mod").write_text('name="a"\npath="C:/a"\n')
    (d / "save games" / "his_campaign.ck3").write_bytes(b"SAVE" * 100)
    (d / "logs" / "error.log").write_text("old log\n")
    return d


def snap(guard, docs, tmp_path):
    return guard.snapshot("testbox", docs, backups=tmp_path / "backups")


def test_untouched_folder_has_no_differences(guard, docs, tmp_path):
    b = snap(guard, docs, tmp_path)
    assert guard.differences(docs, b) == []
    assert guard.check(docs, b) == 0


def test_changed_dlc_load_is_reported_and_restored_byte_exact(guard, docs, tmp_path):
    original = (docs / "dlc_load.json").read_bytes()
    b = snap(guard, docs, tmp_path)
    (docs / "dlc_load.json").write_text(json.dumps({"enabled_mods": ["mod/x.mod"], "disabled_dlcs": []}))
    assert ("changed", "protected", "dlc_load.json") in guard.differences(docs, b)
    assert guard.restore(docs, b) == 0
    assert (docs / "dlc_load.json").read_bytes() == original


def test_vanished_and_new_protected_files_are_put_back_and_moved_aside(guard, docs, tmp_path):
    b = snap(guard, docs, tmp_path)
    (docs / "pdx_settings.txt").unlink()
    (docs / "mod" / "MIGRATE_TEST__layer.mod").write_text('path="C:/layer"\n')
    diff = guard.differences(docs, b)
    assert ("vanished", "protected", "pdx_settings.txt") in diff
    assert ("new", "protected", "mod/MIGRATE_TEST__layer.mod") in diff
    assert guard.restore(docs, b) == 0
    assert (docs / "pdx_settings.txt").read_text() == "settings = { x = 1 }\n"
    assert not (docs / "mod" / "MIGRATE_TEST__layer.mod").exists()
    assert (b / "added" / "mod" / "MIGRATE_TEST__layer.mod").is_file()     # moved, never deleted


def test_saves_are_reported_never_written(guard, docs, tmp_path):
    b = snap(guard, docs, tmp_path)
    (docs / "save games" / "his_campaign.ck3").write_bytes(b"CHANGED")
    (docs / "save games" / "autosave.ck3").write_bytes(b"AUTO")
    (docs / "save games" / "MIGRATE_TEST__ours.ck3").write_bytes(b"OURS")
    diff = guard.differences(docs, b)
    assert ("changed", "saves", "save games/his_campaign.ck3") in diff
    assert ("new", "saves", "save games/autosave.ck3") in diff
    assert not any(rel.endswith("MIGRATE_TEST__ours.ck3") for _, _, rel in diff)
    assert guard.restore(docs, b) == 1                                     # left for a person: still differs
    assert (docs / "save games" / "his_campaign.ck3").read_bytes() == b"CHANGED"   # the guard never writes saves
    assert (docs / "save games" / "autosave.ck3").exists()


def test_ignored_folders_never_count(guard, docs, tmp_path):
    b = snap(guard, docs, tmp_path)
    (docs / "logs" / "error.log").write_text("new log\n")
    (docs / "crashes").mkdir()
    (docs / "crashes" / "dump.dmp").write_bytes(b"x")
    assert guard.differences(docs, b) == []
