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


OLD_PLOT = (b"\t\t7={\n\t\t\ttype=\"sway\"\n\t\t\towner=10\n\t\t\ttarget=20\n\t\t\tartifact=4294967295\n"
            b"\t\t\tprogress=6\n\t\t\tupdate_days=20\n\t\t\tscheme_exposed=no\n\t\t\towner_influence=11\n"
            b"\t\t\tsecrecy=-1\n\t\t\tchance=-1\n\t\t\tscheme_freeze_days=0\n\t\t\tready=yes\n\t\t\tdate=980.9.12\n\t\t}\n")


def test_an_old_plot_is_written_the_way_the_game_converts_it(tmp_path):
    """The game's conversion (measured on 1,334 plots, design 2026-11-05__09-48-21): the old fields dropped, the target
    wrapped, 1.20's starting values in its field order; then R29's thaw (no freeze_data) and secrecy."""
    save, res = run(tmp_path, body(OLD_PLOT))
    assert (b"\t\t7={\n\t\t\ttype=sway\n\t\t\tstatus=continue\n\t\t\towner=10\n\t\t\ttarget={\n\t\t\t\ttype=character\n"
            b"\t\t\t\ttarget=20\n\t\t\t}\n\t\t\tartifact=4294967295\n\t\t\tprogress=6\n\t\t\topportunities=0\n"
            b"\t\t\tupdate_days=20\n\t\t\tsemiyearly_update_days=0\n\t\t\tscheme_exposed=no\n\t\t\tsecrecy=100\n"
            b"\t\t\tdate=980.9.12\n\t\t\tlast_update=1.1.1\n\t\t\tramping_success_chance=0\n\t\t\tbreach=0\n"
            b"\t\t\tphases=0\n\t\t\tnext_id=0\n\t\t}\n") in save.gamestate
    assert (res.extra["converted"], res.extra["invalidated"]) == (1, 0)


def test_a_plot_with_no_owner_target_or_type_is_invalidated(tmp_path):
    """20/20 on the founding save: the game marks exactly these plots invalidated."""
    plot = (b"\t\t8={\n\t\t\towner=4294967295\n\t\t\ttarget=4294967295\n\t\t\tprogress=10\n"
            b"\t\t\towner_influence=52.5\n\t\t\tsecrecy=83\n\t\t\tchance=78\n\t\t\tscheme_freeze_days=0\n"
            b"\t\t\tready=yes\n\t\t\tdate=984.2.3\n\t\t}\n")
    save, res = run(tmp_path, body(plot, OLD_PLOT))
    g = save.gamestate
    assert b"\t\t8={\n\t\t\tstatus=invalidated\n\t\t\towner=4294967295\n" in g and b"7={\n\t\t\ttype=sway\n\t\t\tstatus=continue" in g
    assert (res.extra["converted"], res.extra["invalidated"]) == (2, 1)


def test_the_conversion_alone_keeps_the_plot_frozen_as_the_game_does():
    """What the identity probe compares against the game's re-save: the game's freeze_data block, kept frozen."""
    from ck3_save_migrator.rules.to_1_20 import convert_old_scheme, scheme_fields, scheme_text
    ind, f = scheme_fields(OLD_PLOT[OLD_PLOT.index(b"{") + 1:OLD_PLOT.rindex(b"}")])
    out = scheme_text(convert_old_scheme(f, ind), ind)
    assert out.endswith(b"\t\t\tnext_id=0\n\t\t\tfreeze_data={\n\t\t\t\tfrozen=yes\n\t\t\t\tscheme_freeze_days=0\n"
                        b"\t\t\t\treason=\"\"\n\t\t\t}\n\t\t")
    assert b"secrecy=-1" in out and b"owner_influence" not in out
    assert b"\tchance=" not in out and b"\tready=" not in out          # (ramping_success_chance is 1.20's own)


def test_a_frozen_murder_runs_again_with_its_secrecy_and_agent_slots(tmp_path):
    save, res = run(tmp_path, body(scheme(1, b"murder")))
    g = save.gamestate
    assert b"scheme_freeze_days" not in g and b"\t\t\tsecrecy=20\n" in g
    assert g.count(b"agent_slots={") == 2
    assert b"\t\t\t\tid=0\n\t\t\t\tcharacter=4294967295\n\t\t\t\tcontribution=0\n\t\t\t\ttype=agent_assassin\n" \
           b"\t\t\t\tscheme=1\n" in g and b"type=agent_thug" in g and b"\t\t\tnext_id=2\n\t\t}\n" in g
    assert (res.matched, res.extra["secrecy_set"], res.extra["agent_slots_added"]) == (1, 1, 1)
    # where 1.20 itself puts them: after opportunities, before update_days (109 native plots, s10)
    assert g.index(b"opportunities=0") < g.index(b"agent_slots={") < g.index(b"update_days") \
        if b"update_days" in g else g.index(b"opportunities=0") < g.index(b"agent_slots={") < g.index(b"secrecy=")


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


def test_the_old_games_agents_take_the_new_positions_strongest_first(tmp_path):
    """1.8's owner_agent blocks (agents who had joined) are seated in the new positions by their old influence; one
    more than fit is counted as without a slot, and the old blocks go."""
    agents = (b"\t\t\towner_agent={\n\t\t\t\tcharacter=21\n\t\t\t\tinfluence=5\n\t\t\t}\n"
              b"\t\t\towner_agent={\n\t\t\t\tcharacter=22\n\t\t\t\tinfluence=40\n\t\t\t\texposed=yes\n\t\t\t}\n"
              b"\t\t\towner_agent={\n\t\t\t\tcharacter=23\n\t\t\t\tinfluence=9\n\t\t\t}\n")
    s = scheme(1, b"murder").replace(b"\t\t\tdate=", agents + b"\t\t\tdate=")
    living = b"living={\n" + b"".join(b"%d={\n\tfirst_name=\"A\"\n}\n" % c for c in (21, 22, 23)) + b"}\n"
    save, res = run(tmp_path, living + body(s))
    g = save.gamestate
    assert b"owner_agent" not in g
    assert b"id=0\n\t\t\t\tcharacter=22\n" in g and b"id=1\n\t\t\t\tcharacter=23\n" in g      # 40, then 9
    assert (res.extra["old_agents_seated"], res.extra["old_agents_without_a_slot"]) == (2, 1)


def test_running_twice_changes_nothing_more(tmp_path):
    save, _ = run(tmp_path, body(scheme(1, b"murder"), scheme(2, b"sway")))
    once = save.gamestate
    ctx = RuleContext()
    ctx.game_dir = tmp_path / "game"
    res = R29.run(save, ctx)
    assert save.gamestate == once and res.matched == 0
