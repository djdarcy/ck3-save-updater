"""custom_faiths_census: the save's own faiths (those with a name=), their template, religion and following.

Answers "were there several variants of Way of Scarcity?" from the save itself: every faith entry in
religion/faiths that carries its own name, with its template, its religion, its doctrines, and how many living
characters and counties follow it.

Usage: python -I tests/one-offs/custom_faiths_census.py <gamestate (decompressed text)>
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ck3_save_migrator import gamestate as gs  # noqa: E402


def field(body: bytes, key: str) -> str | None:
    m = re.search(rb'(?m)^\t\t\t' + key.encode() + rb'="?([^"\n]*)"?\s*$', body)
    return m.group(1).decode("utf-8", "replace") if m else None


def main():
    g = Path(sys.argv[1]).read_bytes()
    rel = gs.locate(g, "religion/religions")
    religions = {}
    for e in gs.iter_entries(g, *rel.body):
        tag = re.search(rb'tag="?([^"\s]+)', g[e.open:e.close])
        religions[e.key.decode()] = tag.group(1).decode() if tag else "?"
    fb = gs.locate(g, "religion/faiths")
    faiths = {e.key.decode(): g[e.open:e.close] for e in gs.iter_entries(g, *fb.body)}
    liv = gs.find_section(g, "living")
    followers = Counter(m.group(1).decode() for m in re.finditer(rb'\n\tfaith=(\d+)', g[liv.open:liv.close]))
    cm = gs.locate(g, "county_manager/counties")
    counties = Counter(m.group(1).decode() for m in re.finditer(rb'\n\t+faith=(\d+)', g[cm.open:cm.close]))
    print(f"faiths in the save: {len(faiths)}; with their own name=: "
          f"{sum(1 for b in faiths.values() if field(b, 'name'))}")
    for fid, b in faiths.items():
        name = field(b, "name")
        if not name:
            continue
        docs = re.findall(rb'doctrine="?([a-z0-9_]+)', b)
        print(f"\n{fid}: name={name!r} template={field(b, 'template')} religion={religions.get(field(b, 'religion') or '', field(b, 'religion'))}"
              f" living followers={followers.get(fid, 0)} counties={counties.get(fid, 0)}")
        print(f"   doctrines ({len(docs)}): {', '.join(d.decode() for d in docs)}")
    wos_like = [fid for fid, b in faiths.items() if b"carcity" in b]
    print(f"\nfaith entries mentioning 'carcity' anywhere: {wos_like}")


if __name__ == "__main__":
    main()
