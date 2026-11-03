"""The player's docs stay true to the tool.

- The glossary (docs/glossary.md) has an entry for every verdict word and block header `status` prints: status runs
  on fixtures that reach each verdict, and on no save, and every capitalised header it prints must be an entry's
  heading. A header added to the plan without a glossary entry fails here, naming it.
- Every relative link in README.md and docs/*.md points at a file that exists, and a link to a heading of a
  Markdown file points at a heading that exists.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from ck3_save_migrator import cli
from tests import test_update as TU
from tests.fixtures.make_ck3 import build_ck3
from tests.test_update import game, old_save

saves = TU.saves
no_reference_from_the_environment = TU.no_reference_from_the_environment

ROOT = Path(__file__).resolve().parents[1]
GLOSSARY = ROOT / "docs" / "glossary.md"
# a line that starts with a word (or words) in capitals: a verdict ("READY  ...", "ALREADY CURRENT  ..."), a block
# header ("SAVE  file: ...") or a refusal ("REFUSED: ...")
_HEADER = re.compile(r"^([A-Z]{3,}(?: [A-Z]{2,})*)(?=[ :]|$)")


def headings(md: Path) -> list[str]:
    return [m.group(1).strip() for m in re.finditer(r"(?m)^#{1,6} +(.+?) *$", md.read_text(encoding="utf-8"))]


def printed_headers(out: str) -> set[str]:
    return {m.group(1) for line in out.splitlines() if (m := _HEADER.match(line))}


@pytest.fixture
def status_outputs(tmp_path, saves, capsys) -> dict[str, str]:
    """status --plain on a save for each verdict, and with no save."""
    g = game(tmp_path)
    old = old_save(saves)
    cur = saves / "Current.ck3"
    cur.write_bytes(build_ck3(meta=TU.REF_META, body=TU.REF_BODY + b"random_seed=5\n"))
    runs = {
        "READY": ["status", str(old), "--game-dir", str(g), "--reference", "none"],
        "ALREADY CURRENT": ["status", str(cur), "--game-dir", str(g)],
        "NOTHING TO DO": ["status", str(old), "--game-dir", str(g), "--reference", "none", "--rules", "R8"],
        "REFUSED": ["status", str(old), "--game-dir", str(game(tmp_path, "1.21.0", "Newer"))],
        "no save": ["status", "--game-dir", str(g)],
    }
    out = {}
    for name, argv in runs.items():
        cli.main(argv + ["--plain"])
        o, e = capsys.readouterr()
        out[name] = o + e
    return out


def test_each_fixture_reaches_its_verdict(status_outputs):
    for verdict in ("READY", "ALREADY CURRENT", "NOTHING TO DO", "REFUSED"):
        assert verdict in printed_headers(status_outputs[verdict]), verdict
    assert "SAVES" in printed_headers(status_outputs["no save"])


def test_every_header_and_verdict_status_prints_has_a_glossary_entry(status_outputs):
    printed = set().union(*(printed_headers(o) for o in status_outputs.values()))
    assert {"SAVE", "GAME", "GAP", "PATCHES", "OUTPUT"} <= printed          # the collection itself works
    missing = sorted(printed - set(headings(GLOSSARY)))
    assert not missing, f"no glossary entry (a '### <word>' heading in docs/glossary.md) for: {', '.join(missing)}"


# --------------------------------------------------------------------------- links
_LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)\)|!\[[^\]]*\]\(([^)\s]+)\)")


def slug(heading: str) -> str:
    """GitHub's anchor for a heading: lower case, punctuation dropped (but - and _ kept), spaces to hyphens."""
    s = re.sub(r"[`*]", "", heading.strip().lower())
    s = re.sub(r"[^\w\- ]", "", s)
    return s.replace(" ", "-")


def anchors(md: Path) -> set[str]:
    out, seen = set(), {}
    for h in headings(md):
        base = slug(h)
        n = seen.get(base, 0)
        out.add(base if n == 0 else f"{base}-{n}")
        seen[base] = n + 1
    return out


DOCS = [ROOT / "README.md", *sorted((ROOT / "docs").glob("*.md"))]


@pytest.mark.parametrize("md", DOCS, ids=[str(p.relative_to(ROOT)) for p in DOCS])
def test_relative_links_point_at_files_and_headings_that_exist(md):
    bad = []
    for m in _LINK.finditer(md.read_text(encoding="utf-8")):
        target = m.group(1) or m.group(2)
        if re.match(r"^[a-z][a-z0-9+.-]*:", target):                 # http:, https:, mailto:
            continue
        path, _, anchor = target.partition("#")
        dest = (md.parent / path).resolve() if path else md
        if not dest.exists():
            bad.append(f"{target}: no such file")
        elif anchor and dest.suffix == ".md" and anchor not in anchors(dest):
            bad.append(f"{target}: no heading #{anchor} in {dest.name}")
    assert not bad, f"{md.relative_to(ROOT)}: " + "; ".join(bad)
