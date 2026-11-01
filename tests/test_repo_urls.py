"""The repository was renamed to djdarcy/ck3-save-updater (2026-11-01): no tracked file links the old name, and the
package's URLs (what PyPI shows) name the new one. The old name stays where it is deliberate: the config and cache
folders, the ck3-save-migrator command alias and the ck3_save_migrator package."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from ck3_save_migrator.patches.model import tomllib

ROOT = Path(__file__).resolve().parents[1]
OLD = re.compile(r"github\.com/djdarcy/ck3-save-migrator", re.I)


def tracked() -> list[Path]:
    if shutil.which("git") is None or not (ROOT / ".git").exists():
        pytest.skip("not a git checkout")
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [ROOT / f for f in out.splitlines() if f and not f.startswith("private/")]


def test_no_tracked_file_links_the_old_repository():
    hits = []
    for f in tracked():
        try:
            text = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        hits += [f"{f.relative_to(ROOT)}:{i}" for i, ln in enumerate(text.splitlines(), 1) if OLD.search(ln)]
    assert hits == []


def test_the_package_urls_name_the_new_repository():
    urls = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["urls"]
    assert urls and all(u.startswith("https://github.com/djdarcy/ck3-save-updater") for u in urls.values())


def test_the_deliberate_old_names_are_kept():
    proj = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert proj["scripts"]["ck3-save-migrator"] == "ck3_save_migrator.cli:main"
    from ck3_save_migrator import config
    assert config.APP == "ck3-save-migrator"
