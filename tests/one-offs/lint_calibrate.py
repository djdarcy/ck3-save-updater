"""Calibrate lint's reject families against a real error.log from loading the same save.

Usage: python -I tests/one-offs/lint_calibrate.py <error.log> <save.ck3> [<reference .ck3>] [--mods]

Without --mods, mods are left out of the game data (the A6c launches ran with no mods). Prints, per family:
predicted, observed, and the difference; names for cultures; the key-reference names lint and the game
disagree on.
"""
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from ck3_save_migrator import lint as L  # noqa: E402
from ck3_save_migrator import savefile as sf  # noqa: E402
from ck3_save_migrator.cli import find_game_dir  # noqa: E402

FAMILIES = [  # (lint check prefix, error.log pattern)
    ("Unexpected DNA string length", r"Unexpected DNA string length"),
    ("Unexpected token: owner_influence", r"Unexpected token: owner_influence"),
    ("Unexpected token: exposure_type", r"Unexpected token: exposure_type"),
    ("Unexpected token: exposure_marker", r"Unexpected token: exposure_marker"),
    ("Failed to read key reference", r"Failed to read key reference"),
    ("Unknown on action", r"Unknown on action"),
    ("Unknown dynasty template", r"Unknown dynasty template"),
    ("Unexpected token: ready", r"Unexpected token: ready"),
    ("Unexpected token: localization_key", r"Unexpected token: localization_key"),
    ("Unexpected token: renamed", r"Unexpected token: renamed"),
    ("is not a valid title template", r"is not a valid title template"),
    ("Duplicate landed title name", r"Duplicate landed title name"),
]


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    log = Path(args[0]).read_text(encoding="utf-8", errors="replace").splitlines()
    save = sf.read_save(args[1])
    ref = sf.read_save(args[2]).gamestate if len(args) > 2 else None
    game = find_game_dir(None)
    mods = L.workshop_mod_dirs(save.meta, game) if "--mods" in sys.argv else []
    data = L.load_game_data(game, ref, mods)
    rep = L.lint_gamestate(save.gamestate, known=data)
    found = {f.check: f for f in rep.findings if f.severity == "reject"}
    print(f"game data: {', '.join(data.sources)}; defined keys {len(data.defined):,}, dna length {data.dna_length}")
    print(f"{'family':40} {'predicted':>10} {'observed':>10} {'diff':>8}")
    for prefix, pat in FAMILIES:
        pred = sum(f.count for c, f in found.items() if c.startswith(prefix))
        obs = sum(1 for line in log if re.search(pat, line))
        diff = f"{(pred - obs) / obs * 100:+.1f}%" if obs else ("ok" if not pred else "new")
        print(f"{prefix:40} {pred:>10,} {obs:>10,} {diff:>8}")
    obs_c = sorted(set(re.findall(r"Failed to fetch a valid culture '([^']+)'", "\n".join(log))))
    pred_c = next((f.examples for c, f in found.items() if c.startswith("Failed to fetch")), [])
    print(f"cultures: predicted {pred_c}  observed {obs_c}")
    obs_k = Counter(m.group(1) for line in log for m in [re.search(r"Failed to read key reference: ([^:]+):", line)] if m)
    # lint keeps only the top examples; recompute the full predicted set for the comparison
    pred_k = Counter({k.decode(errors="replace"): n for k, n in L.unresolved_references(save.gamestate, data).items()})
    miss = sorted(((k, n) for k, n in obs_k.items() if k not in pred_k), key=lambda kn: -kn[1])
    extra = sorted(((k, n) for k, n in pred_k.items() if k not in obs_k), key=lambda kn: -kn[1])
    print(f"key references the game logged but lint missed: {len(miss)} names, {sum(n for _, n in miss):,} lines; {miss[:12]}")
    print(f"key references lint predicted but the game did not log: {len(extra)} names, {sum(n for _, n in extra):,}; {extra[:12]}")


if __name__ == "__main__":
    main()
