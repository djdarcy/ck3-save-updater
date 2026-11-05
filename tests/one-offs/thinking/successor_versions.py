"""P4 of goal 2026-11-05__09-39-46 (#7 criterion 3): for each R25 row, the game version that made its change.
Walks the game versions held under private/data/versions (1.7.2 .. 1.20.0) and the installed game, and per row prints
the last version whose common/<folder> defines the old key and the first that defines each new key. A pattern row
(old is a regex) counts any key it matches whole. Known answer: scholar_perk is defined in 1.8.2 and not in 1.20.1.2.
Usage: python -I successor_versions.py"""
import re
import sys
from pathlib import Path

sys.path.insert(0, r"C:\code\ck3-save-migrator")
from ck3_save_migrator.rules.to_1_20 import SUCCESSORS  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
VERS = Path(r"C:\code\ck3-save-migrator\private\data\versions")
LIVE = Path(r"E:\SteamLibrary\steamapps\common\Crusader Kings III")
ORDER = ["1.7.2", "1.8.2", "1.9.2", "1.10.2", "1.11.5", "1.12.5", "1.13.2", "1.14.3", "1.15.0", "1.16.2",
         "1.17.1", "1.18.4", "1.19.0", "1.20.0", "1.20.1.2"]
DEF = re.compile(rb"(?m)^\s*([A-Za-z0-9_.-]+)\s*=\s*\{")
cache: dict[tuple[str, str], set[str] | None] = {}


def defined(ver: str, folder: str) -> set[str] | None:
    """Top-level keys under game/common/<folder> in that version (None when the version lacks the folder)."""
    if (ver, folder) not in cache:
        root = (LIVE if ver == "1.20.1.2" else VERS / ver) / "game" / "common" / folder
        if not root.is_dir():
            cache[ver, folder] = None
        else:
            keys = set()
            for f in root.rglob("*.txt"):
                t = re.sub(rb"#[^\n]*", b"", f.read_bytes())
                keys.update(k.decode() for k in DEF.findall(t) if t[:0] == b"")  # noqa: SIM
            cache[ver, folder] = keys
    return cache[ver, folder]


def has(ver, folder, key, pattern=False):
    keys = defined(ver, folder)
    if keys is None:
        return None
    return any(re.fullmatch(key, k) for k in keys) if pattern else key in keys


assert has("1.8.2", "lifestyle_perks", "scholar_perk") and not has("1.20.1.2", "lifestyle_perks", "scholar_perk"), \
    "known answer failed"
for s in SUCCESSORS:
    pattern = bool(re.search(r"[\\(\[]", s.old))
    old_in = [v for v in ORDER if has(v, s.folder, s.old, pattern)]
    missing = [v for v in ORDER if has(v, s.folder, s.old, pattern) is None]
    news = s.new.split() if isinstance(s.new, str) and "\\" not in s.new else []
    new_first = {n: next((v for v in ORDER if has(v, s.folder, n)), None) for n in news}
    gone = ORDER[ORDER.index(old_in[-1]) + 1] if old_in and old_in[-1] != ORDER[-1] else None
    print(f"{s.old[:55]:55}  last defined {old_in[-1] if old_in else '-':8} removed in {gone or '-':8} "
          f"new first {new_first}  (folder missing in {missing or 'none'})")
