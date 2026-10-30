"""R23 nickname-text: write ``nickname_text="<text>"`` after every ``nickname=KEY`` that lacks it.

A tiny game folder and a tiny mod folder hold English localization (UTF-8 with a byte-order mark, as the game's
files are); one save holds a character for each case: a plain key (quoted and not), templated keys for a man and a
woman, a key only the mod defines, a key the mod overrides, a key under the game's ``replace/`` folder, a key with
no text anywhere, a key whose text has a template code the rule does not render, a character that already has the
text, a character without a nickname, and nicknamed dead characters in both dead sections.
"""

from __future__ import annotations

import difflib
from pathlib import Path

import pytest

from ck3_save_migrator import savefile as sf
from ck3_save_migrator.rules import REGISTRY, RuleContext
from tests.fixtures.make_ck3 import build_ck3

R23 = next(r for r in REGISTRY if r.id == "R23")
META = b'meta_data={\n\tsave_game_version=8\n\tversion="1.8.1"\n}\n'

GAME_NICKS = (
    "l_english:\n"
    ' nick_the_victorious:0 "the Victorious"\n'
    ' nick_the_victorious_desc:0 "a description, never a nickname"\n'
    ' nick_the_tuatha_de_danann: "the Tuatha Dé Danann"\n'
    ' nick_fabulous_she_he:0 "Fabulous [CHARACTER.GetSheHe|U], [CHARACTER.GetFirstNameNoTooltip|U]"\n'
    ' nick_the_blood_motherfather:0 "the Blood-[CHARACTER.GetMotherFather|U]"\n'
    ' nick_scoped:0 "the [ROOT.Char.GetTitle]"\n'
    ' nick_overridden:0 "the Game Text"\n'
    ' nick_replaced:0 "the Base Text"\n'
    ' # nick_commented:0 "never read"\n'
)
GAME_NAMES = 'l_english:\n aedh:0 "Áed"\n'
GAME_REPLACE = 'l_english:\n nick_replaced:0 "the Replaced Text"\n'
MOD_NICKS = 'l_english:\n VIET_nick_crow_lady:0 "the Crow Lady"\n nick_overridden:0 "the Mod Text"\n'


def bom(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\xef\xbb\xbf" + text.encode("utf-8"))


@pytest.fixture
def folders(tmp_path):
    game = tmp_path / "steam" / "Crusader Kings III" / "game"
    bom(game / "localization" / "english" / "nicknames_l_english.yml", GAME_NICKS)
    bom(game / "localization" / "english" / "names" / "character_names_l_english.yml", GAME_NAMES)
    bom(game / "localization" / "replace" / "english" / "fixes_l_english.yml", GAME_REPLACE)
    mod = tmp_path / "mods" / "2227658180"
    bom(mod / "localization" / "english" / "VIET_nicknames_l_english.yml", MOD_NICKS)
    return game, mod


def char(cid, name, extra=""):
    return f'{cid}={{\n\tfirst_name="{name}"\n{extra}\tbirth=900.1.1\n}}\n'


BODY = (
    "living={\n"
    + char(1, "Brian", "\tnickname=nick_the_victorious\n")
    + char(2, "Uilleam", '\tnickname="nick_the_tuatha_de_danann"\n')
    + char(3, "aedh", "\tnickname=nick_fabulous_she_he\n")
    + char(4, "aedh", "\tfemale=yes\n\tnickname=nick_fabulous_she_he\n")
    + char(5, "Gormlaith", "\tfemale=yes\n\tnickname=nick_the_blood_motherfather\n")
    + char(6, "Nu", "\tnickname=VIET_nick_crow_lady\n")
    + char(7, "Odo", "\tnickname=nick_overridden\n")
    + char(8, "Ivo", "\tnickname=nick_replaced\n")
    + char(9, "Nemo", "\tnickname=nick_nowhere\n")
    + char(10, "Scope", "\tnickname=nick_scoped\n")
    + char(11, "Done", '\tnickname=nick_the_victorious\n\tnickname_text="the Victorious"\n')
    + char(12, "Plain", "")
    + "}\n"
    "dead_unprunable={\n"
    + char(20, "Echmarcach", "\tnickname=nick_the_victorious\n")
    + "}\n"
    "characters={\n\tdead_prunable={\n"
    + char(30, "Gone", '\tnickname="nick_the_tuatha_de_danann"\n')
    + "\t}\n}\n"
).encode("utf-8")

EXPECTED = {
    1: "the Victorious", 2: "the Tuatha Dé Danann", 3: "Fabulous He, Áed", 4: "Fabulous She, Áed",
    5: "the Blood-Mother", 6: "the Crow Lady", 7: "the Mod Text", 8: "the Replaced Text",
    20: "the Victorious", 30: "the Tuatha Dé Danann",
}


def run(folders, body=BODY, mods=True):
    game, mod = folders
    save = sf.parse_save(build_ck3(meta=META, body=body))
    res = R23.run(save, RuleContext(game_dir=game, mod_dirs=[mod] if mods else []))
    return save, res


def entry(g: bytes, cid: int) -> bytes:
    s = g.index(f"\n{cid}={{\n".encode()) + 1
    return g[s:g.index(b"\n}", s)]


def test_each_nickname_gets_its_text_right_after_it(folders):
    save, _ = run(folders)
    g = save.gamestate
    for cid, text in EXPECTED.items():
        e = entry(g, cid)
        nick_line = next(ln for ln in e.split(b"\n") if ln.startswith(b"\tnickname="))
        assert nick_line + b'\n\tnickname_text="' + text.encode("utf-8") + b'"\n' in e + b"\n", cid
        assert e.count(b"nickname_text=") == 1, cid


def test_the_report_counts_and_sources(folders):
    _, res = run(folders)
    assert res.extra["found"] == 12 and res.matched == 12 and res.edited == 10
    assert res.extra["by_source"] == {"game": 8, "mod": 2}            # the crow lady and the override
    assert sorted((t["id"], t["text"]) for t in res.extra["templated"]) == \
        [("3", "Fabulous He, Áed"), ("4", "Fabulous She, Áed"), ("5", "the Blood-Mother")]


def test_unresolved_keys_are_reported_and_left_untouched(folders):
    save, res = run(folders)
    assert {(u["id"], u["key"]) for u in res.extra["unresolved"]} == {("9", "nick_nowhere"), ("10", "nick_scoped")}
    assert "no English localization" in next(u["reason"] for u in res.extra["unresolved"] if u["id"] == "9")
    assert "ROOT.Char.GetTitle" in next(u["reason"] for u in res.extra["unresolved"] if u["id"] == "10")
    for cid in (9, 10):
        assert b"nickname_text" not in entry(save.gamestate, cid)
    assert b"[" not in save.gamestate and b"$" not in save.gamestate


def test_a_key_only_a_mod_defines_needs_the_mod(folders):
    save, res = run(folders, mods=False)
    assert b"nickname_text" not in entry(save.gamestate, 6)
    assert b'nickname_text="the Game Text"' in entry(save.gamestate, 7)       # vanilla text without the mod
    assert ("6", "VIET_nick_crow_lady") in {(u["id"], u["key"]) for u in res.extra["unresolved"]}


def test_characters_with_the_text_or_without_a_nickname_are_untouched(folders):
    save, _ = run(folders)
    assert entry(save.gamestate, 11) == entry(BODY, 11) and entry(save.gamestate, 12) == entry(BODY, 12)


def test_the_rule_only_inserts(folders):
    save, res = run(folders)
    before, after = (META + BODY).split(b"\n"), save.gamestate.split(b"\n")
    ops = difflib.SequenceMatcher(None, before, after, autojunk=False).get_opcodes()
    assert {op for op, *_ in ops} == {"equal", "insert"}
    inserted = [ln for op, _, _, j1, j2 in ops if op == "insert" for ln in after[j1:j2]]
    assert len(inserted) == res.edited and all(ln.startswith(b'\tnickname_text="') for ln in inserted)


def test_a_second_run_edits_nothing(folders):
    save, _ = run(folders)
    once = save.gamestate
    res = R23.run(save, RuleContext(game_dir=folders[0], mod_dirs=[folders[1]]))
    assert save.gamestate == once and res.edited == 0
    assert res.matched == 2                     # only the two unresolved still lack the text


def test_without_a_game_folder_nothing_is_guessed(folders):
    save = sf.parse_save(build_ck3(meta=META, body=BODY))
    res = R23.run(save, RuleContext(game_dir=None, mod_dirs=[]))
    assert res.edited == 0 and save.gamestate == META + BODY
    assert all("no game folder" in u["reason"] for u in res.extra["unresolved"])


def test_a_text_with_a_quote_or_a_backslash_is_escaped(folders, tmp_path):
    game, mod = folders
    bom(mod / "localization" / "english" / "odd_l_english.yml",
        'l_english:\n nick_odd:0 "the \\"Odd\\" One \\\\ X"\n')
    body = b"living={\n" + char(1, "Odd", "\tnickname=nick_odd\n").encode() + b"}\n"
    save, _ = run(folders, body=body)
    assert b'\tnickname_text="the \\"Odd\\" One \\\\ X"\n' in save.gamestate
