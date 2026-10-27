"""variant_drop_events: a diagnostic copy of a save with chosen queued events (triggered_event blocks) removed.

2026-10-27: the migrated save's sim thread loops forever on 987.11.8; two culture events are queued for that day
(culture_hybridization_emergence_events on 33569451, culture_divergence_emergence_events on 16838976). Dropping
them and seeing whether the game passes the date says whether one of them is the trigger. Never a migration.

Usage: python -I tests/one-offs/variant_drop_events.py <in.ck3> <out.ck3> <on_action>[,<on_action>...] <date>
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator import savefile as sf  # noqa: E402


def main():
    src, out, actions, date = sys.argv[1], sys.argv[2], sys.argv[3].split(","), sys.argv[4]
    save = sf.read_save(src)
    g = save.gamestate
    drops = []
    for b in gs.find_sections(g, "triggered_event"):
        body = g[b.open:b.close]
        m = re.search(rb'on_action="?([\w.]+)', body)
        if m and m.group(1).decode() in actions and re.search(rb"date=" + re.escape(date.encode()) + rb"\b", body):
            s, e = gs.removal_span(g, b.start, b.close + 1)
            drops.append((s, e, m.group(1).decode()))
    for s, e, _ in sorted(drops, reverse=True):
        save.replace_range(s, e, b"")
    sf.write_save(save, out, force=True)
    print(f"dropped {len(drops)}: {[d[2] for d in drops]}; wrote {out}")


if __name__ == "__main__":
    main()
