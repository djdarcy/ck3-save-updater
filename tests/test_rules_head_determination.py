"""R32 gives a carried culture the head determination its template's definition declares (the after-goal-pass goal,
S3; measured on both 1.20.1.2 references: 488 of 488 cultures carry their template's declared value)."""

from __future__ import annotations

from ck3_save_migrator import rules as R
from ck3_save_migrator import savefile as sf
from ck3_save_migrator.rules import to_1_20 as T
from tests.fixtures.make_ck3 import DEFAULT_META, build_ck3


def make_save(body: bytes):
    return sf.parse_save(build_ck3(meta=DEFAULT_META, body=body))

DEFS = {
    "game/common/culture/cultures/00_a.txt":
        "akan = {\n\tcolor = { 1 1 1 }\n\thead_determination = head_determination_domain\n}\n"
        "bedouin = {\n\tcolor = { 1 1 1 }\n\thead_determination = head_determination_herd\n}\n"
        "nameless = {\n\tcolor = { 1 1 1 }\n}\n",
}
GAMESTATE = (b"culture_manager={\n\tcultures={\n"
             b"\t\t1={\n\t\t\tculture_template=\"akan\"\n\t\t\tname=\"Akan\"\n\t\t}\n"
             b"\t\t2={\n\t\t\tculture_template=\"bedouin\"\n\t\t\tname=\"Bedouin\"\n\t\t}\n"
             b"\t\t3={\n\t\t\tculture_template=\"akan\"\n\t\t\thead_determination=head_determination_herd\n\t\t}\n"
             b"\t\t4={\n\t\t\tname=\"Made In Play\"\n\t\t}\n"
             b"\t\t5={\n\t\t\tculture_template=\"nameless\"\n\t\t}\n"
             b"\t}\n}\n")


def game(tmp_path, defs=DEFS):
    for rel, text in defs.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text, encoding="utf-8")
    return tmp_path / "game"


def run(tmp_path, gamestate=GAMESTATE, defs=DEFS, mods=()):
    save = make_save(gamestate)
    res = T.r32_head_determination(save, R.RuleContext(game_dir=game(tmp_path, defs), mod_dirs=list(mods)),
                                   R.select("R32")[0])
    return save.gamestate, res


def culture(g: bytes, cid: bytes) -> bytes:
    i = g.index(b"\t\t" + cid + b"={")
    return g[i:g.index(b"\t\t}", i)]


def test_each_carried_culture_takes_its_template_s_declared_value(tmp_path):
    g, res = run(tmp_path)
    assert b"head_determination=head_determination_domain" in culture(g, b"1")
    assert b"head_determination=head_determination_herd" in culture(g, b"2")
    assert res.extra["written"] == {"head_determination_domain": 1, "head_determination_herd": 1}


def test_a_culture_that_has_one_is_left_as_it_is(tmp_path):
    g, _ = run(tmp_path)
    assert culture(g, b"3").count(b"head_determination=") == 1 and b"_herd" in culture(g, b"3")


def test_a_field_written_on_one_line_as_the_game_writes_it_counts_as_there(tmp_path):
    # the game's own cultures (and those R16 transplants) put head_determination after tabs on one line: the S3
    # scratch update wrote a second one into 55 such cultures until the check read any whitespace
    one_line = (b"culture_manager={\n\tcultures={\n\t\t6={\n\t\t\tculture_template=\"akan\"\n"
                b"\t\t\tethos=ethos_egalitarian\t\t\thead_determination=head_determination_herd\t\t}\n\t}\n}\n")
    g, res = run(tmp_path, gamestate=one_line)
    assert g.count(b"head_determination=") == 1 and res.matched == 0


def test_no_template_or_no_declaration_stays_without_and_is_counted(tmp_path):
    g, res = run(tmp_path)
    assert b"head_determination" not in culture(g, b"4") and b"head_determination" not in culture(g, b"5")
    assert res.extra["left"] == {"no culture_template (a culture made in play)": 1, "template nameless has no definition": 1}


def test_a_mod_s_definition_replaces_the_game_s(tmp_path):
    mod = tmp_path / "mod"
    (mod / "common/culture/cultures").mkdir(parents=True)
    (mod / "common/culture/cultures/zz.txt").write_text("akan = {\n\thead_determination = head_determination_herd\n}\n",
                                                        encoding="utf-8")
    g, _ = run(tmp_path, mods=[mod])
    assert b"head_determination=head_determination_herd" in culture(g, b"1")


def test_without_the_game_s_files_nothing_is_written(tmp_path):
    save = make_save(GAMESTATE)
    before = save.gamestate
    res = T.r32_head_determination(save, R.RuleContext(game_dir=None), R.select("R32")[0])
    assert save.gamestate == before and "skipped" in res.extra
