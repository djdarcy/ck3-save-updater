"""Shared test fixtures for ck3-save-migrator."""

import pytest


@pytest.fixture(autouse=True)
def hermetic_discovery(monkeypatch):
    """No test finds the real game install or the project's reference save by itself.

    Both are machine-dependent (and reading them made every migrate test ~10 s slower once lint ran by
    default). A test that wants one passes --game-dir / --reference, or a RuleContext, explicitly; explicit
    values still win. Subprocess tests inherit these variables.
    """
    monkeypatch.setenv("CK3_GAME_DIR", "none")
    monkeypatch.setenv("CK3_REFERENCE_SAVE", "none")


@pytest.fixture(autouse=True)
def hermetic_config(monkeypatch, tmp_path_factory):
    """No test reads or writes the player's own config file (rules turned off with `disable`, trusted packs) or
    packs folder (beside the config): each test gets an empty one of its own, also inherited by subprocesses. It
    is a temporary folder apart from the test's own ``tmp_path``, so a test that checks what a command wrote there
    does not see the packs folder the commands create."""
    monkeypatch.setenv("CK3SM_CONFIG", str(tmp_path_factory.mktemp("ck3sm") / "ck3sm-config" / "config.toml"))
    # the block-index cache is on by default (0.3.23): never in the real temp folder from a test
    monkeypatch.setenv("CK3UPDATE_CACHE_DIR", str(tmp_path_factory.mktemp("ck3idx")))


@pytest.fixture
def tmp_project(tmp_path):
    """A temporary project directory for a test to work in."""
    project_dir = tmp_path / "test_project"
    project_dir.mkdir()
    return project_dir
