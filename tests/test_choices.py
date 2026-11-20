"""The player's choices: the --auto grammar and the per-province prompt (goal 2026-11-19__22-43-27, S4).

CONSEQUENCE: 6 (contract) -- --auto is a public CLI contract djdarcy designed (HOLD 22:0x-22:5x); a misread answer
replaces a district the player wanted kept, or a script that worked on one save errors on the next.

The concept: entries apply left to right and later wins; all / all=mygame / all=newgame mean each kind's own default,
campaign-first or new-game-first answer; an unknown kind or answer errors naming the valid ones; at a terminal
a<letter> settles every remaining question of the kind; without a terminal the default is taken; every answer is
recorded with how it was reached.
"""
import io

import pytest

from ck3_save_migrator import choices as CH


def test_the_grammar_all_mygame_newgame_and_later_wins():
    assert CH.parse_auto(["all"]) == {"resources": "m"}
    assert CH.parse_auto(["all=mygame"]) == {"resources": "r"}
    assert CH.parse_auto(["all=newgame"]) == {"resources": "k"}
    assert CH.parse_auto(["all=newgame,resources=m"]) == {"resources": "m"}           # later wins
    assert CH.parse_auto(["resources=replace", "all=newgame"]) == {"resources": "k"}   # the option repeated, still later wins
    assert CH.parse_auto(["resources=keep"]) == {"resources": "k"}                     # the word or the letter


@pytest.mark.parametrize("spec, says", [("pastures=k", "the questions are: resources"),
                                        ("resources=x", "the answers are k (keep), m (minor), r (replace)"),
                                        ("all=mine", "all=mygame or all=newgame")])
def test_an_unknown_kind_or_answer_errors_naming_what_is_valid(spec, says):
    with pytest.raises(CH.AutoError, match=says.replace("(", r"\(").replace(")", r"\)")):
        CH.parse_auto([spec])


def test_at_a_terminal_a_letter_settles_the_rest_and_the_header_shows_once():
    err = io.StringIO()
    a = CH.Asker(interactive=True, stdin=io.StringIO("am\n"), stderr=err)
    got = [a.ask("resources", f"province {p}", header="Quarries: 89 provinces ...") for p in (1, 2, 3)]
    assert got == ["m", "m", "m"]
    assert err.getvalue().count("Quarries: 89 provinces") == 1 and err.getvalue().count("province 2") == 0
    assert [h for *_, h in a.record] == ["asked", "rest", "rest"]          # the report tells them from --auto


def test_the_plan_says_how_each_question_will_be_answered_before_the_run(monkeypatch):
    from types import SimpleNamespace as NS

    from ck3_save_migrator import cli
    said = []
    monkeypatch.setattr(cli, "say", lambda level, text, *a, **k: said.append(text))
    plan = NS(steps=[NS(id="R46", will_run=True), NS(id="R42", will_run=True)])
    outs = []
    for auto, asking in ((["resources=r"], False), (None, True), (None, False)):
        said.clear()
        cli.say_choices(plan, NS(auto=auto), asking)
        outs.append(" ".join(said))
    assert "resources: replace (--auto)" in outs[0]
    assert "asked for each province" in outs[1]
    assert "minor (the default" in outs[2]
    said.clear()
    cli.say_choices(NS(steps=[NS(id="R46", will_run=False)]), NS(auto=None), True)
    assert said == []                                                 # a rule that will not run asks nothing


def test_enter_takes_the_default_a_bad_answer_reprompts_and_no_terminal_takes_the_default():
    a = CH.Asker(interactive=True, stdin=io.StringIO("x\nk\n\n"), stderr=io.StringIO())
    assert [a.ask("resources", "p1"), a.ask("resources", "p2")] == ["k", "m"]
    quiet = CH.Asker(interactive=False)
    assert quiet.ask("resources", "p1") == "m" and quiet.record == [("resources", "p1", "m", "default")]
    pre = CH.Asker(auto=CH.parse_auto(["all=mygame"]), interactive=True, stdin=io.StringIO(""), stderr=io.StringIO())
    assert pre.ask("resources", "p1") == "r" and pre.record[0][3] == "auto"
