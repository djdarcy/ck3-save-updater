"""meta_identity_probe: which metadata fields tell a fresh game's save from a migrated save the game re-saved?
(2026-10-30)

The update driver will pick a reference save automatically (a save written by the target version at the campaign's
date). The director: "the pick must never choose a save that descends from the one being updated, nor one this tool
wrote; ... measure which meta fields a fresh game and a migrated save differ in before choosing." This prints every
depth-1 key of each save's meta_data with its value (short), side by side, plus whether the gamestate carries any
playthrough-style identifier, so the discriminator is chosen from measured fields.

Usage: python -I tests/one-offs/meta_identity_probe.py <label=save.ck3> [...]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ck3_save_migrator.savefile import read_save  # noqa: E402

KEY = re.compile(rb"^\t?([A-Za-z_][A-Za-z0-9_]*)=(.*)$", re.M)
IDLIKE = re.compile(rb"\n\t?(playthrough_id|playthrough_uuid|game_id|session_id|uuid|ironman_manager|campaign_id|"
                    rb"seed|random_seed|start_date|game_start_date|bookmark|meta_player_name|meta_house_name|"
                    rb"meta_date|meta_title_name)=([^\n]{0,80})")


def _text_save(path):
    """A kind-00 (uncompressed text) save, as the game writes in debug mode: (meta_data block, text head)."""
    raw = Path(path).read_bytes()
    raw = raw[raw.find(b"\n") + 1:]
    i = raw.find(b"meta_data={")
    depth, j = 0, i
    while j < len(raw):
        c = raw[j:j + 1]
        if c == b"{":
            depth += 1
        elif c == b"}":
            depth -= 1
            if depth == 0:
                break
        j += 1
    return raw[i + len(b"meta_data={"):j], raw


def scan(path):
    try:
        s = read_save(path)
        meta, gamestate = bytes(s.meta or b""), s.gamestate
    except Exception as ex:  # kind 00 text saves: read them as text, say so
        if "kind 00" not in str(ex):
            raise
        meta, gamestate = _text_save(path)
    s = type("S", (), {"gamestate": gamestate})
    keys = {}
    depth = 0
    for line in meta.split(b"\n"):
        if depth <= 1:
            m = re.match(rb"^\t?([A-Za-z_][A-Za-z0-9_]*)=(.*)$", line)
            if m and line.count(b"\t") <= 1:
                keys.setdefault(m.group(1).decode(), m.group(2)[:60].decode("utf-8", "replace"))
        depth += line.count(b"{") - line.count(b"}")
    head = s.gamestate[:400000]
    ids = {m.group(1).decode(): m.group(2).decode("utf-8", "replace") for m in IDLIKE.finditer(head)}
    return keys, ids


def main():
    cols = []
    for a in sys.argv[1:]:
        label, _, p = a.partition("=")
        cols.append((label, *scan(p)))
    allkeys = sorted(set().union(*[c[1] for c in cols]))
    print("META depth-0/1 keys:")
    for k in allkeys:
        vals = [c[1].get(k, "--") for c in cols]
        mark = "" if len(set(vals)) == 1 else "  *"
        print(f"  {k:28s} " + " | ".join(f"{c[0]}: {v[:34]}" for c, v in zip(cols, vals)) + mark)
    print("\nID-like keys near the start of the gamestate:")
    for c in cols:
        print(f"  {c[0]}: {c[2]}")


if __name__ == "__main__":
    main()
