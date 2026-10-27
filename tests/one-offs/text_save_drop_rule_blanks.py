"""text_save_drop_rule_blanks: a loadable copy of a plain-text (-debug_mode) save whose game_rules carry "" entries.

2026-10-27: the 1.20 game writes "" in game_rules settings for every rule it cannot find (rules of mods the
campaign once had and the playset lacks: VIET events, ICC, the Community Flavor Pack, VTA, farewell_chaplain;
13 in every save it wrote from a migrated campaign, 0 from the vanilla control) and then refuses its own save
("Failed to read key reference ... near line 23"). R4 removes such blanks in a migration; this does the same
to a text save for a diagnostic reload. The header's meta length is rewritten. Writes a new file; never in place.

Usage: python -I tests/one-offs/text_save_drop_rule_blanks.py <text save.ck3> <out.ck3>
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

HEADER = re.compile(rb"^SAV([0-9a-fA-F]{2})00([0-9a-fA-F]{8})([0-9a-fA-F]{8})(\r?\n)")
SETTINGS = re.compile(rb"(settings=\{)([^}]*)(\})")


def clean(b: bytes) -> tuple[bytes, int]:
    n = 0

    def drop(m):
        nonlocal n
        toks = m.group(2).split(b" ")
        kept = [t for t in toks if t.strip() != b'""']
        n += len(toks) - len(kept)
        return m.group(1) + b" ".join(kept) + m.group(3)
    return SETTINGS.sub(drop, b), n


def main():
    src, out = sys.argv[1:3]
    if Path(out).resolve() == Path(src).resolve():
        sys.exit("refusing to write over the source")
    raw = Path(src).read_bytes()
    h = HEADER.match(raw)
    if not h:
        sys.exit("not a plain-text (kind 00) save")
    meta_len = int(h.group(3), 16)
    body = raw[h.end():]
    meta, rest = clean(body[:meta_len]), clean(body[meta_len:])
    head = b"SAV" + h.group(1) + b"00" + h.group(2) + f"{len(meta[0]):08x}".encode() + h.group(4)
    Path(out).write_bytes(head + meta[0] + rest[0])
    print(f"wrote {out}: {meta[1]} blank(s) dropped from the meta, {rest[1]} from the gamestate; "
          f"meta length {meta_len} -> {len(meta[0])}")


if __name__ == "__main__":
    main()
