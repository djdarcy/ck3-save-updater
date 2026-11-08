"""POC: can R15 run from a built-in table of the old map instead of the old game folder?

djdarcy 2026-11-07: "including the titles so users aren't dependent on old assets ... giving people titles from a
moment in time". R15 (deadtitles.classify) reads only title_tree(old landed_titles): each title's parent and each
barony's province. Prediction: classify's mappings from a table dumped from 1.8.2 equal those from the 1.8.2 folder,
on the founding save. Control: the same table with one barony's province changed must give different mappings.
Writes the table to argv[1] (JSON); reads nothing else outside the repo's private/data.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from ck3_save_migrator import deadtitles as D  # noqa: E402
from ck3_save_migrator.lint import defined_title_keys  # noqa: E402
from ck3_save_migrator.savefile import read_save  # noqa: E402

DATA = ROOT / "private" / "data"
OLD = DATA / "versions" / "1.8.2" / "game" / "common" / "landed_titles"
GAME = Path(r"E:\SteamLibrary\steamapps\common\Crusader Kings III\game")
NEW = GAME / "common" / "landed_titles"
SAVE = DATA / "originals" / "save games" / "Arch-Abbot_Beidh_of_Omni_Church_Council_987_10_27_husband_died.ck3"

parent, province = D.title_tree(OLD)
Path(sys.argv[1]).write_text(json.dumps({"parent": parent, "province": province}, separators=(",", ":")),
                             encoding="utf-8")
table = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))

g = read_save(SAVE).gamestate
_, conv = defined_title_keys(GAME)
real_tree = D.title_tree


def flat(maps):
    return sorted((m.key, m.kind, m.cls, tuple(m.successors)) for m in maps)


def from_table(t):
    def tree(d):
        return (t["parent"], t["province"]) if Path(d) == OLD else real_tree(d)
    return tree


folder = flat(D.classify(g, OLD, NEW, set(conv)))
D.title_tree = from_table(table)
tabled = flat(D.classify(g, OLD, NEW, set(conv)))
bad = json.loads(json.dumps(table))
some = next(k for k in bad["province"] if any(m[0] == k for m in folder)) if any(
    m[0] in bad["province"] for m in folder) else next(iter(bad["province"]))
bad["province"][some] = bad["province"][some] + 9999
D.title_tree = from_table(bad)
control = flat(D.classify(g, OLD, NEW, set(conv)))
D.title_tree = real_tree
print(f"table: {len(table['parent']):,} titles, {len(table['province']):,} baronies, "
      f"{Path(sys.argv[1]).stat().st_size:,} bytes")
print(f"mappings from the folder: {len(folder)}; from the table: {len(tabled)}; equal: {folder == tabled}")
print(f"control (province of {some} changed): equal to the folder's: {control == folder}  (must be False)")
