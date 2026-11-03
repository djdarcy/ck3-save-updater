"""`ck3update -h` says where to start and lists every command once, grouped; a bare `ck3update` prints where to start.

djdarcy, 2026-11-02: the flat list of twenty commands "could feel intimidating"; ccs's epilogue was the model.
"""
import pytest

from ck3_save_migrator import cli, helptext


def top_help(capsys) -> str:
    with pytest.raises(SystemExit) as exc:
        cli.main(["-h"])
    assert exc.value.code == 0
    return capsys.readouterr().out


def test_every_command_is_in_exactly_one_group_and_no_group_names_a_missing_one():
    """The drift guard: a new command left out of GROUPS would vanish from -h, since the flat list is gone."""
    parser_cmds = set(cli.build_parser()._subparsers._group_actions[0].choices)
    listed = [c for _, rows in helptext.GROUPS for _, cmds, _ in rows for c in cmds]
    assert len(listed) == len(set(listed)), "a command is listed twice"
    assert set(listed) == parser_cmds


def test_help_starts_with_status_and_shows_each_group(capsys):
    out = top_help(capsys)
    assert out.splitlines()[0].endswith("<command> ...")     # not the twenty-name brace
    assert 'ck3update status "My Save"' in out and 'ck3update update "My Save"' in out
    assert out.index("start here:") < out.index("updating a save:")
    for heading, _ in helptext.GROUPS:
        assert f"\n{heading}:\n" in out
    assert "{inspect,migrate" not in out
    assert "show a save's header" not in out                  # inspect's long line: the flat list is gone


def test_help_fits_an_80_column_console(capsys):
    out = top_help(capsys)
    assert max(len(line) for line in out.splitlines()) <= 79


def test_bare_command_prints_where_to_start_and_succeeds(capsys):
    assert cli.main([]) == 0
    got = capsys.readouterr()
    assert got.err == ""
    assert got.out.startswith(helptext.DESCRIPTION)
    assert "start here:" in got.out and got.out.rstrip().endswith("ck3update -h lists every command.")


def test_a_command_help_opens_with_its_one_line_description(capsys):
    with pytest.raises(SystemExit):
        cli.main(["status", "-h"])
    out = capsys.readouterr().out
    assert "what `update` would do to a save" in out.split("positional arguments:")[0]


def test_an_unknown_command_is_still_an_error(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["bogus"])
    assert exc.value.code == 2
