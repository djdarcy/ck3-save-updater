"""Wait for a named save to appear (and stop growing) in the game's save folder, then copy, inspect and extract it.

Usage: python tests/one-offs/wait_for_save.py <save-stem> [timeout-seconds]
Copies to private/data/originals/reference-1.20/, prints `inspect`, extracts header_meta.txt +
gamestate to private/data/extracted/<stem>/, and prints the top-level section sizes. Read-only
on the game folder.
"""
import os
import re
import shutil
import sys
import time
import zipfile
import io
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from ck3_save_migrator import savefile as sf  # noqa: E402

stem = sys.argv[1]
timeout = int(sys.argv[2]) if len(sys.argv) > 2 else 3600
saves = Path(os.environ["USERPROFILE"]) / "Documents" / "Paradox Interactive" / "Crusader Kings III" / "save games"
src = saves / f"{stem}.ck3"
t0 = time.time()
last = -1
while True:
    if src.exists():
        size = src.stat().st_size
        if size == last and size > 0:
            break
        last = size
    if time.time() - t0 > timeout:
        print(f"timeout: {src} did not appear")
        sys.exit(1)
    time.sleep(3)
print(f"save appeared: {src} ({last:,} bytes)", flush=True)
dst = ROOT / "private" / "data" / "originals" / "reference-1.20" / src.name
shutil.copy2(src, dst)
save = sf.read_save(dst)
h = save.header
print(f"copied to {dst}")
print(f"header {h.raw.rstrip().decode()}  kind {h.kind:02x} {save.kind_name}  meta {h.meta_len:,}  warnings {save.warnings}")
for k in (b"save_game_version", b"version", b"portraits_version", b"meta_date", b"meta_player_name", b"meta_title_name"):
    m = re.search(rb"(?m)^\t" + k + rb"=(.*)$", save.meta)
    print(f"  {k.decode():18} {m.group(1).decode(errors='replace') if m else '-'}")
mods = re.search(rb"(?m)^\tmods=\{([^}]*)\}", save.meta)
print(f"  mods               {mods.group(1).decode().strip() if mods else '(none)'}")
out = ROOT / "private" / "data" / "extracted" / stem
out.mkdir(parents=True, exist_ok=True)
(out / "header_meta.txt").write_bytes(h.raw + save.meta)
(out / "gamestate").write_bytes(save.gamestate)
gs = save.gamestate
pos = [(m.start(), m.group(1).decode()) for m in re.finditer(rb"(?m)^([A-Za-z_][\w.]*)\s*=", gs)]
sizes = {}
for i, (p, k) in enumerate(pos):
    end = pos[i + 1][0] if i + 1 < len(pos) else len(gs)
    sizes[k] = sizes.get(k, 0) + end - p
print(f"extracted to {out}: gamestate {len(gs):,} bytes, {len(sizes)} top-level keys")
for k, s in sorted(sizes.items(), key=lambda kv: -kv[1])[:25]:
    print(f"  {s:>12,}  {k}")
