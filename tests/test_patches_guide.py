"""docs/writing-a-patch.md cannot drift: its shipped examples equal the shipped files, and its own examples run."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from ck3_save_migrator import savefile as sf
from ck3_save_migrator.patches import apply_patch, load_patch, shipped_pack_folder, status
from ck3_save_migrator.patches.pack import CONTEXT_FIELDS
from tests.fixtures.make_ck3 import build_ck3

GUIDE = (Path(__file__).resolve().parents[1] / "docs" / "writing-a-patch.md").read_text(encoding="utf-8")


def block(marker: str) -> str:
    m = re.search(r"<!-- " + re.escape(marker) + r" -->\n```toml\n(.*?)```", GUIDE, re.S)
    assert m, f"no block after <!-- {marker} -->"
    return m.group(1)


@pytest.mark.parametrize("folder", ["R1-opinions-converging", "R4-game-rule-blanks", "R5-empty-keys",
                                    "R7-version-bump", "R11-empty-modifiers"])
def test_each_shipped_example_is_the_shipped_file(folder):
    assert block(f"shipped: {folder}") == shipped_pack_folder().joinpath(folder, "patch.toml").read_text(
        encoding="utf-8")


def load(tmp_path: Path, marker: str):
    d = tmp_path / marker
    d.mkdir()
    (d / "patch.toml").write_text(block(f"example: {marker}"), encoding="utf-8")
    return load_patch(d, from_disk=True, context_fields=CONTEXT_FIELDS)


def test_the_rename_example_runs(tmp_path):
    save = sf.parse_save(build_ck3(meta=b"meta_data={\n\told_key=1\n\tother=2\n}\n", body=b"x={\n\told_key=3\n}\n"))
    apply_patch(save, load(tmp_path, "rename"), {})
    assert save.gamestate == b"meta_data={\n\tnew_key=1\n\tother=2\n}\nx={\n\told_key=3\n}\n"


def test_the_insert_example_runs_once(tmp_path):
    p = load(tmp_path, "insert")
    save = sf.parse_save(build_ck3(meta=b"meta_data={\n\tversion=1\n}\n", body=b""))
    apply_patch(save, p, {})
    assert save.gamestate == b"meta_data={\n\tversion=1\n\tmigrated_by=yes\n}\n"
    assert status(save.gamestate, p) == "done"
    apply_patch(save, p, {})
    assert save.gamestate.count(b"migrated_by") == 1
