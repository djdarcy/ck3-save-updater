"""``gamediff``: two game folders compared definition by definition, and what of the difference a save names.

Two small synthetic ``game`` folders are written into ``tmp_path``: definitions added, removed and changed, and
changes of whitespace or comments only (not changes). The save is synthetic too.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ck3_save_migrator import cli
from ck3_save_migrator import gamediff as gd
from tests.fixtures.make_ck3 import build_ck3

OLD = {
    "common/traits/00_traits.txt": (
        "﻿craven = { prowess = -2 }\n"                              # a byte-order mark right before a key
        "# traits of the old version\n"
        "brave = {\n\tprowess = 2\n\tcategory = personality\n}\n"
        "gone_trait = { diplomacy = 1 }\n"
        "unused_gone = { diplomacy = 1 }\n"                               # removed, but the save never names it
        "unused_changed = { diplomacy = 1 }\n"                            # changed, but the save never names it
        "spaced = {\n    learning   =  1\n}\n"
        "commented = {\n\tstewardship = 1 # a comment inside the definition\n} # and one after it\n"
        "@local_value = 5\n"
    ),
    "common/traits/01_more.txt": "moved_trait = { martial = 1 }\n",
    "common/culture/cultures/00_cultures.txt": "norse = { color = rgb { 10 20 30 } }\nsaxon = { color = rgb { 1 2 3 } }\n",
    "common/religion/religions/00_germanic.txt": (
        "germanic_religion = {\n\tfamily = rf_pagan\n\tfaiths = {\n"
        "\t\tnorse_pagan = { icon = norse }\n\t\tasatru = { icon = asatru }\n\t}\n}\n"
    ),
    "common/landed_titles/00_titles.txt": (
        "e_scandinavia = {\n\tcolor = { 1 1 1 }\n"
        "\tk_norway = {\n\t\tcolor = { 2 2 2 }\n\t\td_vestlandet = {\n\t\t\tc_bergen = { b_bergen = { province = 1 } }\n"
        "\t\t}\n\t}\n"
        "\tk_old_kingdom = { color = { 3 3 3 } }\n}\n"
    ),
    "common/game_rules/00_rules.txt": (
        "difficulty = {\n\tdefault = normal_difficulty\n\tnormal_difficulty = { }\n\thard_difficulty = { }\n}\n"
    ),
    "common/modifiers/00_mods.txt": "old_bonus = { monthly_prestige = 1 }\n",
    "events/norse.txt": "namespace = norse\nnorse.0001 = { type = character_event }\n",
    "history/characters/norse.txt": "100 = { name = Ragnar }\n",
    "map_data/definition.csv": "province;red;green;blue;x;x\n1;10;20;30;Bergen;x;\n2;11;21;31;Oslo;x;\n",
}

NEW = {
    "common/traits/00_traits.txt": (
        "brave = {\n\tprowess = 3\n\tcategory = personality\n}\n"        # changed
        "craven = { prowess = -2 }\n"                                     # unchanged (no BOM, no comment: same)
        "new_trait = { diplomacy = 2 }\n"                                 # added; gone_trait removed
        "unused_changed = { diplomacy = 2 }\n"
        "spaced = { learning = 1 }\n"                                     # whitespace only: unchanged
        "commented = { stewardship = 1 }\n"                               # comment only: unchanged
        "@local_value = 6\n"                                              # a constant: not a definition
    ),
    "common/traits/02_more.txt": "moved_trait = { martial = 1 }\n",      # moved between files: unchanged
    "common/culture/cultures/00_cultures.txt": "norse = { color = rgb { 10 20 31 } }\nsaxon = { color = rgb { 1 2 3 } }\n",
    "common/religion/religions/00_germanic.txt": (
        "germanic_religion = {\n\tfamily = rf_pagan\n\tfaiths = {\n"
        "\t\tnorse_pagan = { icon = norse_new }\n\t}\n}\n"                # norse_pagan changed, asatru removed
    ),
    "common/landed_titles/00_titles.txt": (
        "e_scandinavia = {\n\tcolor = { 1 1 1 }\n"
        "\tk_norway = {\n\t\tcolor = { 2 2 2 }\n\t\td_vestlandet = {\n\t\t\tc_bergen = { b_bergen = { province = 7 } }\n"
        "\t\t}\n\t}\n}\n"                                                 # b_bergen changed, k_old_kingdom removed
    ),
    "common/game_rules/00_rules.txt": (
        "difficulty = {\n\tdefault = normal_difficulty\n\tnormal_difficulty = { }\n}\n"   # an option removed
    ),
    "common/modifiers/00_mods.txt": "new_bonus = { monthly_prestige = 1 }\n",
    "events/norse.txt": "namespace = norse\nnorse.0001 = { type = character_event }\nnorse.0002 = { }\n",
    "history/characters/norse.txt": "100 = { name = Ragnar }\n",
    "map_data/definition.csv": "province;red;green;blue;x;x\n1;10;20;30;Bergen;x;\n2;11;21;31;Osloby;x;\n",
}


def game(root: Path, files: dict) -> Path:
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return root


@pytest.fixture
def games(tmp_path):
    return game(tmp_path / "old" / "game", OLD), game(tmp_path / "new" / "game", NEW)


def diff(games):
    old, new = games
    return {g: d.as_dict() for g, d in gd.compare(gd.read_definitions(old), gd.read_definitions(new)).items()}


def test_added_removed_and_changed_by_folder(games):
    d = diff(games)
    assert d["common/traits"] == {"added": ["new_trait"], "removed": ["gone_trait", "unused_gone"],
                                  "changed": ["brave", "unused_changed"]}
    assert d["common/culture/cultures"] == {"added": [], "removed": [], "changed": ["norse"]}
    assert d["common/modifiers"] == {"added": ["new_bonus"], "removed": ["old_bonus"], "changed": []}
    assert d["events"] == {"added": ["norse.0002"], "removed": [], "changed": []}
    assert d["map_data/definition.csv"] == {"added": [], "removed": [], "changed": ["2"]}


def test_whitespace_comments_byte_order_marks_and_moves_are_not_changes(games):
    d = diff(games)
    traits = d["common/traits"]
    for same in ("craven", "spaced", "commented", "moved_trait"):
        assert same not in traits["changed"] + traits["added"] + traits["removed"], same
    assert not any(k.startswith("@") or k == "namespace" for g in d.values() for v in g.values() for k in v)
    assert "history/characters" not in d                                # unchanged groups are left out


def test_nested_definitions_are_their_own_groups(games):
    d = diff(games)
    assert d["common/landed_titles"] == {"added": [], "removed": ["k_old_kingdom"], "changed": ["b_bergen"]}
    assert d["common/religion/religions (faiths)"] == {"added": [], "removed": ["asatru"], "changed": ["norse_pagan"]}
    assert d["common/religion/religions"]["changed"] == ["germanic_religion"]
    assert d["common/game_rules (options)"] == {"added": [], "removed": ["hard_difficulty"], "changed": []}


def test_a_parent_title_is_not_changed_by_a_change_inside_a_nested_title(games):
    d = diff(games)
    assert "e_scandinavia" not in d["common/landed_titles"]["changed"]
    assert "k_norway" not in d["common/landed_titles"]["changed"]


SAVE_META = b'meta_data={\n\tversion="1.8.1"\n\tgame_rules={\n\t\tsettings={ hard_difficulty }\n\t}\n}\n'
SAVE_BODY = (b'traits_lookup={ "brave" "gone_trait" "craven" }\n'
             b'landed_titles={\n\tlanded_titles={\n\t\t1={\n\t\t\tkey="k_old_kingdom"\n\t\t}\n\t}\n}\n'
             b'religion={\n\tfaiths={\n\t\t1={\n\t\t\ttemplate="asatru"\n\t\t}\n\t}\n}\n'
             b'culture_manager={ cultures={ 1={ culture_template="norse" } } }\n'
             b'living={ 1={ modifier="old_bonus" } }\n')


def test_the_save_names_which_removed_or_changed_keys(games):
    d = gd.compare(gd.read_definitions(games[0]), gd.read_definitions(games[1]))
    names = gd.save_names(SAVE_META + SAVE_BODY)
    uses = gd.used_by_save(d, names)
    assert uses == {
        "traits": {"removed": ["gone_trait"], "changed": ["brave"]},
        "titles": {"removed": ["k_old_kingdom"], "changed": []},
        "faiths": {"removed": ["asatru"], "changed": []},
        "cultures": {"removed": [], "changed": ["norse"]},
        "modifiers": {"removed": ["old_bonus"], "changed": []},
        "game rules": {"removed": ["hard_difficulty"], "changed": []},
    }


def test_the_command_reads_only_and_writes_only_its_json(games, tmp_path, capsys):
    old, new = games
    save = tmp_path / "save.ck3"
    save.write_bytes(build_ck3(meta=SAVE_META, body=SAVE_BODY))
    before = {p: p.stat().st_mtime_ns for p in tmp_path.rglob("*")}
    out_json = tmp_path / "diff.json"
    assert cli.main(["gamediff", str(old), str(new), "--save", str(save), "--json", str(out_json)]) == 0
    out = capsys.readouterr().out
    assert "common/traits: 1 added, 2 removed, 2 changed" in out
    assert "removed : gone_trait" in out and "the save names 7 of the removed or changed keys" in out
    assert "traits     removed : gone_trait" in out and "game rules removed : hard_difficulty" in out
    assert {p: p.stat().st_mtime_ns for p in tmp_path.rglob("*") if p != out_json} == before
    data = json.loads(out_json.read_text(encoding="utf-8"))
    assert data["groups"]["common/traits"]["added"] == ["new_trait"]
    assert data["save"]["uses"]["traits"]["removed"] == ["gone_trait"]


def test_the_save_is_scanned_once_not_once_per_key(games, monkeypatch):
    """One pass of the name pattern over the gamestate, however many keys are compared."""
    calls = []
    real = gd._NAME

    class Counting:
        def finditer(self, data, *a):
            calls.append(len(data))
            return real.finditer(data, *a)
    monkeypatch.setattr(gd, "_NAME", Counting())
    d = gd.compare(gd.read_definitions(games[0]), gd.read_definitions(games[1]))
    gd.used_by_save(d, gd.save_names(SAVE_META + SAVE_BODY))
    assert calls == [len(SAVE_META + SAVE_BODY)]


def test_a_missing_game_folder_is_refused(tmp_path, capsys):
    assert cli.main(["gamediff", str(tmp_path / "nope"), str(tmp_path)]) == 1
    assert "not a folder" in capsys.readouterr().err


def test_long_key_lists_are_cut_on_screen_but_complete_in_json(tmp_path, capsys):
    many = {"common/traits/t.txt": "".join(f"t{i} = {{ }}\n" for i in range(40))}
    old, new = game(tmp_path / "a", {"common/traits/t.txt": ""}), game(tmp_path / "b", many)
    assert cli.main(["gamediff", str(old), str(new), "--json", str(tmp_path / "d.json")]) == 0
    assert "... and 10 more (see --json)" in capsys.readouterr().out
    assert len(json.loads((tmp_path / "d.json").read_text(encoding="utf-8"))["groups"]["common/traits"]["added"]) == 40
