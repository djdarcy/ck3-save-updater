"""Shared test fixtures for ck3-save-migrator."""

import pytest


@pytest.fixture
def tmp_project(tmp_path):
    """A temporary project directory for a test to work in."""
    project_dir = tmp_path / "test_project"
    project_dir.mkdir()
    return project_dir
