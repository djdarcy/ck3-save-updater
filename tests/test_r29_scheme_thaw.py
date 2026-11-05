"""R29 scheme-thaw: the old game's frozen schemes run again, with the secrecy and agent slots 1.20's start-up
gives a scheme started from script (read from the game's and the mods' scheme definitions)."""

from __future__ import annotations

from ck3_save_migrator import savefile as sf
from ck3_save_migrator.rules import REGISTRY, RuleContext
from tests.fixtures.make_ck3 import build_ck3

R29 = next(r for r in REGISTRY if r.id == "R29")
META = b'meta_data={\n\tsave_game_version=8\n\tversion="1.8.1"\n}\n'
TYPES = """murder = {
\tbase_secrecy = { add = secrecy_base_value }
\ton_start = {
\t\tif = {
\t\t\tlimit = {
\t\t\t\tscheme_owner = {
\t\t\t\t\tNOT = { has_variable = agents_added }
\t\t\t\t}
\t\t\t}
\t\t\tadd_agent_slot = agent_assassin
\t\t\tadd_agent_slot = agent_thug
\t\t}
\t}
}
sway = {
\ton_start = { }
}
"""


def scheme(sid, ty, secrecy=b"-1", frozen=True):
    return (b"\t\t%d={\n\t\t\ttype=\"%s\"\n\t\t\towner=10\n\t\t\tprogress=6\n\t\t\tsecrecy=%s\n" % (sid, ty, secrecy)
            + (b"\t\t\tscheme_freeze_days=0\n" if frozen else b"") + b"\t\t\tdate=983.4.23\n\t\t}\n")


def run(tmp_path, body):
    g = tmp_path / "game"
    (g / "common" / "schemes" / "scheme_types").mkdir(parents=True)
    (g / "common" / "schemes" / "scheme_types" / "x.txt").write_text(TYPES, encoding="utf-8")
    save = sf.parse_save(build_ck3(meta=META, body=body))
    ctx = RuleContext()
    ctx.game_dir = g
    return save, R29.run(save, ctx)


def body(*schemes):
    return b"schemes={\n\tactive={\n" + b"".join(schemes) + b"\t}\n}\n"


def test_a_frozen_murder_runs_again_with_its_secrecy_and_agent_slots(tmp_path):
    save, res = run(tmp_path, body(scheme(1, b"murder")))
    g = save.gamestate
    assert b"scheme_freeze_days" not in g and b"\t\t\tsecrecy=20\n" in g
    assert g.count(b"agent_slots={") == 2
    assert b"\t\t\t\tid=0\n\t\t\t\tcharacter=4294967295\n\t\t\t\tcontribution=0\n\t\t\t\ttype=agent_assassin\n" \
           b"\t\t\t\tscheme=1\n" in g and b"type=agent_thug" in g and b"\t\t\tnext_id=2\n\t\t}\n" in g
    assert (res.matched, res.extra["secrecy_set"], res.extra["agent_slots_added"]) == (1, 1, 1)


def test_a_type_without_base_secrecy_gets_100_and_no_slots(tmp_path):
    """1.20 holds 100 for its own schemes of a type with no base_secrecy (sway 403/403 in a played save)."""
    save, res = run(tmp_path, body(scheme(2, b"sway")))
    g = save.gamestate
    assert b"scheme_freeze_days" not in g and b"\t\t\tsecrecy=100\n" in g and b"agent_slots" not in g
    assert (res.matched, res.extra["secrecy_set"], res.extra["agent_slots_added"]) == (1, 1, 0)


def test_a_type_the_game_does_not_define_is_only_thawed(tmp_path):
    save, res = run(tmp_path, body(scheme(4, b"some_mods_scheme")))
    g = save.gamestate
    assert b"scheme_freeze_days" not in g and b"secrecy=-1" in g and b"agent_slots" not in g
    assert (res.matched, res.extra["secrecy_set"]) == (1, 0)


def test_a_scheme_the_new_game_started_is_left_alone(tmp_path):
    save, res = run(tmp_path, body(scheme(3, b"murder", secrecy=b"38", frozen=False)))
    assert res.matched == 0 and b"agent_slots" not in save.gamestate


def test_running_twice_changes_nothing_more(tmp_path):
    save, _ = run(tmp_path, body(scheme(1, b"murder"), scheme(2, b"sway")))
    once = save.gamestate
    ctx = RuleContext()
    ctx.game_dir = tmp_path / "game"
    res = R29.run(save, ctx)
    assert save.gamestate == once and res.matched == 0
