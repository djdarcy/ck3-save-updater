"""v9 blocker sweep (djdarcy 2026-11-05: "Are there any other major categories we haven't checked?"): every quoted
file reference in a save (icons, textures, illustrations: *.dds/*.png/*.tga; 3D models: *_entity) checked against
what the game and the playset's mods ship. Grouped by the field that holds it, with a count of missing references
and of those a known rename fixes (artefact_ -> artifact_).

Usage: python -I file_reference_sweep.py <save> [--mods <mod descriptor> ...]   (no --mods: the test playset)"""
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, r"C:\code\ck3-save-migrator")
from ck3_save_migrator import savefile as sf  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
GAME = Path(r"E:\SteamLibrary\steamapps\common\Crusader Kings III\game")
DOCS = Path(r"C:\Users\Extreme\Documents\Paradox Interactive\Crusader Kings III")
PLAYSET = ["mod/ugc_2220098919.mod", "mod/ugc_2507209632.mod", "mod/ugc_2996881191.mod", "mod/ugc_2220326926.mod",
           "mod/ugc_2531691049.mod", "mod/ugc_2453009990.mod", "mod/ugc_2535753142.mod", "mod/ugc_2600114033.mod",
           "mod/ugc_2216754325.mod", "mod/ugc_3811584019.mod", "mod/ugc_3084203091.mod", "mod/ugc_2886198939.mod",
           "mod/wos_1_20.mod", "mod/ugc_2243723476.mod", "mod/ugc_2227658180.mod", "mod/ugc_2221952570.mod",
           "mod/ugc_2226700455.mod"]
FILE = re.compile(rb'(\w+)="([^"\n]*?\.(?:dds|png|tga))"', re.I)
ENTITY = re.compile(rb'(\w+)="?(\w+_entity)"?')


def mod_root(desc):
    t = (DOCS / desc).read_text(encoding="utf-8-sig", errors="replace")
    m = re.search(r'path\s*=\s*"([^"]+)"', t)
    return Path(m.group(1)) if m else None


def inventory(roots):
    files, entities = set(), set()
    for r in roots:
        g = r / "gfx"
        if not g.is_dir():
            continue
        for p in g.rglob("*"):
            s = p.suffix.lower()
            if s in (".dds", ".png", ".tga"):
                files.add(p.name.lower())
            elif s == ".asset":
                for m in re.finditer(r'name\s*=\s*"?(\w+_entity)"?', p.read_text(encoding="utf-8-sig", errors="replace")):
                    entities.add(m.group(1).lower())
    return files, entities


def main():
    args = sys.argv[1:]
    mods = args[args.index("--mods") + 1:] if "--mods" in args else PLAYSET
    roots = [GAME] + [r for r in (mod_root(m) for m in mods) if r and r.is_dir()]
    print(f"roots: game + {len(roots) - 1} mods")
    files, entities = inventory(roots)
    print(f"inventory: {len(files)} image files, {len(entities)} model entities")
    d = sf.read_save(args[0]).gamestate
    refs, missing, fixable = Counter(), Counter(), Counter()
    examples = defaultdict(Counter)
    for m in FILE.finditer(d):
        key, val = m.group(1).decode(), m.group(2).decode()
        name = val.replace("\\", "/").rsplit("/", 1)[-1].lower()
        refs[key] += 1
        if name not in files:
            missing[key] += 1
            examples[key][name] += 1
            if name.replace("artefact_", "artifact_", 1) in files:
                fixable[key] += 1
    for m in ENTITY.finditer(d):
        key, val = m.group(1).decode() + " (model)", m.group(2).decode().lower()
        refs[key] += 1
        if val not in entities:
            missing[key] += 1
            examples[key][val] += 1
    for key in sorted(refs, key=lambda k: -missing[k]):
        print(f"{key:28} refs {refs[key]:6}  missing {missing[key]:5}  fixed by the spelling rename {fixable[key]:4}")
        for name, n in examples[key].most_common(4):
            print(f"      {n:5}  {name}")


if __name__ == "__main__":
    main()
