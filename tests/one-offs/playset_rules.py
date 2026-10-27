"""playset_rules: fit a save's game rules and mod list to the playset it will be played with.

2026-10-27: every save the 1.20 game writes from a migrated campaign carries "" in game_rules for each rule option
the save names that the loaded game and mods do not define, and the game then refuses its own save ("Failed to read
key reference"). djdarcy decided the migration takes the target playset explicitly; until that rule exists, this
one-off does it for a play save: it reads the game's and each playset mod's common/game_rules/*.txt, keeps only the
options something defines in meta_data/game_rules/settings and the top-level game_rules/setting, and sets
meta_data/mods to the playset's descriptors. Writes a new file; never in place.

Usage: python -I tests/one-offs/playset_rules.py <in.ck3> <out.ck3> <game dir> <descriptor=mod folder>...
  e.g. mod/ugc_2220098919.mod=E:/.../workshop/content/1158310/2220098919
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator import savefile as sf  # noqa: E402

TOKEN = re.compile(r'#[^\n]*|"[^"]*"|\{|\}|[^\s={}"]+|=')


def options(folder: Path) -> set[str]:
    """Every option key of every rule in <folder>/common/game_rules: the blocks inside a rule's block, plus its
    default=. A rule is a top-level `name = { ... }`."""
    out = set()
    d = folder / "common" / "game_rules"
    for f in sorted(d.glob("*.txt")) if d.exists() else []:
        toks = [t for t in TOKEN.findall(f.read_text(encoding="utf-8-sig", errors="replace")) if not t.startswith("#")]
        depth, i = 0, 0
        while i < len(toks):
            t = toks[i]
            if t == "{":
                depth += 1
            elif t == "}":
                depth -= 1
            elif depth == 1 and i + 2 < len(toks) and toks[i + 1] == "=":
                if toks[i + 2] == "{" and t not in ("categories", "flag"):
                    out.add(t)
                elif t == "default":
                    out.add(toks[i + 2].strip('"'))
            i += 1
    return out


def main():
    src, out, game = sys.argv[1], sys.argv[2], Path(sys.argv[3])
    playset = [a.split("=", 1) for a in sys.argv[4:]]
    defined = options(game)
    for _, folder in playset:
        defined |= options(Path(folder))
    save = sf.read_save(src)
    g = save.gamestate
    ep = gs.EditPass()
    dropped = {}
    blocks = []
    try:
        blocks.append(("meta", gs.find_child(g, gs.find_section(g, "meta_data"), "game_rules")))
    except gs.GamestateError:
        pass
    blocks += [("gamestate", b) for b in gs.find_sections(g, "game_rules")]
    for label, gr in blocks:
        for lst in gs.iter_children(g, *gr.body):
            if lst.key not in (b"settings", b"setting") or lst.block is None:
                continue
            for v in gs.iter_children(g, *lst.block.body):
                if v.key is not None or v.block is not None:
                    continue
                val = g[v.start:v.end].decode("utf-8", "replace").strip('"')
                if val and val not in defined:
                    s, e = gs.removal_span(g, v.start, v.end)
                    ep.add(gs.Edit(s, e, b"", "playset", label))
                    dropped.setdefault(label, []).append(val)
    meta = gs.find_section(g, "meta_data")
    mods = next((c for c in gs.iter_children(g, *meta.body) if c.key == b"mods" and c.block is not None), None)
    new_mods = b"{ " + b" ".join(f'"{d}"'.encode() for d, _ in playset) + b" }"
    if mods is not None:            # the braces only: Block.start is the key's start (2026-10-27: replacing from
        ep.add(gs.Edit(mods.block.open, mods.block.end, new_mods, "playset", "meta mods"))  # there lost "mods=")
    ep.apply_to(save)
    sf.write_save(save, out, force=True)
    print(f"wrote {out}: {len(defined)} rule options defined by the game and {len(playset)} mods")
    for label, vals in dropped.items():
        print(f"  {label}: dropped {len(vals)}: {sorted(set(vals))}")
    print(f"  meta mods set to {len(playset)} descriptors")


if __name__ == "__main__":
    main()
