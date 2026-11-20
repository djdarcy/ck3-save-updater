"""Fold the Oracle's glossary draft (2026-11-20__15-55-33) into docs/glossary.md: section A's entries go under the
existing "## Saves and versions" heading (before the next "## "); sections B-E become new "## " sections at the end.
One-off for goal 2026-11-20__16-02-08 S1. Run from the repo root with python -I."""
import re
from pathlib import Path

draft = Path("private/claude/notes/ideas/2026-11-20__15-55-33__both_glossary-additions-for-players.md").read_text(
    encoding="utf-8").replace("\r\n", "\n")
body = draft.split("## Proposed entries", 1)[1].split("\n## Two things the lead", 1)[0]
parts = re.split(r"\n### ([A-E])\. ([^\n]*)\n", body)
sections = {parts[i]: (parts[i + 1], parts[i + 2].strip("\n")) for i in range(1, len(parts), 3)}

g = Path("docs/glossary.md")
text = g.read_text(encoding="utf-8").replace("\r\n", "\n")
head = "## Saves and versions\n"
i = text.index(head)
j = text.find("\n## ", i + len(head))
j = len(text) if j == -1 else j
text = text[:j].rstrip("\n") + "\n\n" + sections["A"][1] + "\n" + text[j:]
for k in "BCDE":
    title = re.sub(r"\s*\(.*\)\s*$", "", sections[k][0]).strip()
    text = text.rstrip("\n") + f"\n\n## {title}\n\n" + sections[k][1] + "\n"
g.write_text(text, encoding="utf-8")
print({k: v[0] for k, v in sections.items()})
