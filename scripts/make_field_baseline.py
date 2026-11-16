"""Write the field baseline of a game-written save: ck3_save_migrator/baselines/<version>/fields.json.

The baseline records, per database, which depth-1 fields the game's own entries carry and the share leaving each
empty -- structure, never values (see ck3_save_migrator/baselines.py). Make one for each game version the tool should
check against without a reference save, from any save that version wrote itself (a fresh game, saved once, is best:
nothing migrated in it). The version is read from the save's own meta_data.

Run: python -I scripts/make_field_baseline.py <game-written save.ck3> [--out <path>] [--check]
     --check: regenerate and compare with the shipped file; exit 1 when they differ.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ck3_save_migrator import baselines as B  # noqa: E402
from ck3_save_migrator.savefile import parse_header, parse_save  # noqa: E402


def gamestate(path: Path) -> bytes:
    data = path.read_bytes()
    h = parse_header(data[:64])
    return data[len(h.raw):] if h.kind == 0 else parse_save(data).gamestate


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("save", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    baseline = B.build_baseline(gamestate(a.save))
    version = baseline["game_version"]
    if not version:
        print(f"{a.save}: no version= in its meta_data; not a save this script can key", file=sys.stderr)
        return 2
    out = a.out or ROOT / "ck3_save_migrator" / "baselines" / version / "fields.json"
    text = B.dumps(baseline)
    if a.check:
        same = out.is_file() and out.read_text(encoding="utf-8") == text
        print(f"{out}: {'identical' if same else 'DIFFERS'}")
        return 0 if same else 1
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {out}: game {version}, {len(baseline['databases'])} databases, "
          f"{sum(len(d['fields']) for d in baseline['databases'].values())} fields")
    return 0


if __name__ == "__main__":
    sys.exit(main())
