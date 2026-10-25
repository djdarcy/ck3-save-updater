"""Unit-3 follow-ups: where 1.20 places title_name_data, and dead titles from the game's own files.

Usage: python -I tests/one-offs/measure_unit3b.py
"""
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from ck3_save_migrator import gamestate as gs  # noqa: E402

OLD = ROOT / "private/data/extracted/987_10_27_husband_died/gamestate"
REF = ROOT / "private/data/extracted/ref_1_20_persia_867/gamestate"
GAME = Path(r"E:\SteamLibrary\steamapps\common\Crusader Kings III\game")
BASELINE_ERR = ROOT / "private/data/runs/2026-10-24__20-19-01__baseline-orig-1.8.1-loadsave/logs/error.log"

ref = REF.read_bytes()
lt = gs.locate(ref, "landed_titles/landed_titles")
pred, succ = Counter(), Counter()
for t in gs.iter_entries(ref, *lt.body):
    keys = [c.key for c in gs.iter_children(ref, *t.body)]
    if b"title_name_data" in keys:
        i = keys.index(b"title_name_data")
        pred[keys[i - 1] if i else b"<first>"] += 1
        succ[keys[i + 1] if i + 1 < len(keys) else b"<last>"] += 1
print("title_name_data predecessor:", dict(pred.most_common(8)))
print("title_name_data successor  :", dict(succ.most_common(8)))

old = OLD.read_bytes()
lt = gs.locate(old, "landed_titles/landed_titles")
opred = Counter()
for t in gs.iter_entries(old, *lt.body):
    keys = [c.key for c in gs.iter_children(old, *t.body)]
    if b"name" in keys:
        i = keys.index(b"name")
        opred[keys[i - 1] if i else b"<first>"] += 1
print("1.8.1 'name' predecessor   :", dict(opred.most_common(8)))

# title templates the installed game defines
defined = set()
for f in (GAME / "common" / "landed_titles").glob("*.txt"):
    txt = f.read_bytes()
    txt = re.sub(rb"#[^\n]*", b"", txt)
    defined.update(m.group(1).decode() for m in re.finditer(rb"(?<![\w.])([hekdcb]_[\w\-']+)\s*=\s*\{", txt))
print(f"game defines {len(defined):,} title templates")

save_keys = []
for t in gs.iter_entries(old, *lt.body):
    k = next((c for c in gs.iter_children(old, *t.body) if c.key == b"key"), None)
    if k is not None:
        save_keys.append(old[k.value_start:k.value_end].strip(b'"').decode())
dyn = [k for k in save_keys if k.startswith("x_")]
missing = [k for k in save_keys if not k.startswith("x_") and k not in defined]
err = BASELINE_ERR.read_text(encoding="utf-8", errors="replace")
logged = re.findall(r"landed_title\.cpp:1169\]: (\S+) is not a valid title template", err)
print(f"save titles {len(save_keys):,}; dynamic x_ {len(dyn):,}; not defined by the game {len(missing)}")
print(f"  equal to the error.log list: {set(missing) == set(logged)}; "
      f"only in ours {sorted(set(missing) - set(logged))[:10]}; only in log {sorted(set(logged) - set(missing))[:10]}")
