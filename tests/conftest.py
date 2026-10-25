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


@pytest.fixture
def tmp_project(tmp_path):
    """A temporary project directory for a test to work in."""
    project_dir = tmp_path / "test_project"
    project_dir.mkdir()
    return project_dir
