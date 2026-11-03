"""Tests for the version module."""

from ck3_save_migrator._version import (
    MAJOR, MINOR, PATCH, PHASE, PROJECT_PHASE,
    get_version, get_base_version, get_display_version, get_pip_version,
    __app_name__,
)


def test_app_name():
    assert __app_name__ == "ck3-save-updater"


def test_version_components():
    assert isinstance(MAJOR, int)
    assert isinstance(MINOR, int)
    assert isinstance(PATCH, int)


def test_phase_valid():
    """PHASE is empty (a stable release) or a string like 'alpha', 'beta', 'rc1'."""
    assert isinstance(PHASE, str)


def test_get_version_returns_string():
    v = get_version()
    assert isinstance(v, str)
    assert len(v) > 0


def test_base_version_format():
    base = get_base_version()
    assert base.startswith(f"{MAJOR}.{MINOR}.{PATCH}")


def test_display_version_includes_project_phase():
    display = get_display_version()
    if PROJECT_PHASE and PROJECT_PHASE != "stable":
        assert PROJECT_PHASE.upper() in display
    else:
        assert display == get_base_version()


def test_pip_version_pep440():
    pip_v = get_pip_version()
    assert "-" not in pip_v
    if PHASE:
        assert any(c.isalpha() for c in pip_v.split(".")[-1])
    else:
        assert all(c.isdigit() or c == "." for c in pip_v)


def test_dash_capital_v_prints_the_version_as_dash_dash_version_does(capsys):
    """`ck3update -V` is the short form of `--version` (djdarcy, 2026-11-03)."""
    import pytest
    from ck3_save_migrator import cli
    outs = []
    for flag in ("-V", "--version"):
        with pytest.raises(SystemExit) as ex:
            cli.main([flag])
        assert ex.value.code == 0
        outs.append(capsys.readouterr().out)
    assert outs[0] == outs[1] == f"{__app_name__} {get_display_version()}\n"
