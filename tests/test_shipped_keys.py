"""No shipped patch writes a key the game does not define (the 0.4.0 goal's S2 guard).

A key the game does not know is reported when the save loads ("Unexpected token": the marker save, 2026-11-01),
so a shipped rule, the shipped example pack, or the guide's examples writing one would teach players to break
their saves. The game's keys come from a save the game wrote itself (tests/fixtures/keys_1_20_1_2.txt, taken by
tests/one-offs/extract_save_keys.py from a fresh 1.20.1.2 game), so this runs without the game.

A key is "written" by `set` (its key), `rename_key` (its new name) and `insert` (every key in the payload).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from ck3_save_migrator import userpacks as U
from ck3_save_migrator.patches import read_pack
from ck3_save_migrator.patches.model import EditSpec

KEYS = Path(__file__).parent / "fixtures" / "keys_1_20_1_2.txt"
PAYLOAD_KEY = re.compile(r"(?:^|[\s{])([A-Za-z_][A-Za-z0-9_.:]*)[ \t]*=")


def game_keys() -> set[str]:
    return {ln for ln in KEYS.read_text(encoding="utf-8").splitlines() if ln and not ln.startswith("#")}


def written(e: EditSpec) -> set[str]:
    if e.op == "set":
        return {e.key}
    if e.op == "rename_key":
        return {e.to}
    if e.op == "insert":
        return set(PAYLOAD_KEY.findall(e.payload or ""))
    return set()


def example_pack(tmp_path: Path):
    folder = tmp_path / "example"
    for rel, text in U.EXAMPLE.items():
        p = folder / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return read_pack(folder)


def test_the_key_list_is_a_real_saves():
    keys = game_keys()
    assert len(keys) > 20000 and {"meta_player_name", "version", "save_game_version", "living"} <= keys


@pytest.mark.parametrize("which", ["built-in", "example"])
def test_no_shipped_patch_writes_a_key_the_game_does_not_define(which, tmp_path):
    pack = read_pack() if which == "built-in" else example_pack(tmp_path)
    keys = game_keys()
    bad = {(p.id, k) for p in pack.ordered() for e in p.edits for k in written(e) if k not in keys}
    assert not bad, f"keys the game does not define, written by {which} patches: {sorted(bad)}"


def test_the_example_changes_the_load_screen_name_once(tmp_path):
    """djdarcy's pick for the sample (2026-11-03): an edit the player can see, of a key the game writes."""
    from ck3_save_migrator import savefile as sf
    from ck3_save_migrator.patches import apply_patch, status
    from tests.fixtures.make_ck3 import build_ck3
    x1 = example_pack(tmp_path).patches["X1"]
    meta = b'meta_data={\n\tversion="1.20.1.2"\n\tmeta_player_name="Arch-Abbot Beidh"\n}\n'
    save = sf.parse_save(build_ck3(meta=meta, body=b""))
    apply_patch(save, x1, {})
    assert b'meta_player_name="Edited with ck3update"' in save.gamestate
    assert b"Arch-Abbot Beidh" not in save.gamestate
    once = save.gamestate
    assert status(save.gamestate, x1) == "done"
    apply_patch(save, x1, {})
    assert save.gamestate == once


def test_the_guard_catches_an_unknown_key():
    """The guard itself: the old example's insert would fail it."""
    old = EditSpec(index=1, paths=("meta_data",), op="insert", position="end", payload="\tmigrated_by=yes\n")
    assert written(old) == {"migrated_by"} and "migrated_by" not in game_keys()
