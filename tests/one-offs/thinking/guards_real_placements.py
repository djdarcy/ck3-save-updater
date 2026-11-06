"""What the #6 guards did on the founding save: the rows R17 reports for the cases the guards commit names
(Constantinople's seat, Arslan's herders and Begluk, the Byzantine noble families, holy orders), plus the lock-step
counts. Same run as tests/test_rules.py::test_real_987_new_map_transplant.
Usage: python -I guards_real_placements.py"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from ck3_save_migrator import rules as R  # noqa: E402
from ck3_save_migrator import savefile as sf  # noqa: E402

SAVE = ROOT / "private/data/originals/save games/Arch-Abbot_Beidh_of_Omni_Church_Council_987_10_27_husband_died.ck3"
REF = ROOT / "private/data/originals/reference-1.20/ref_1_20_987_10_27.ck3"
GAME = Path(r"E:\SteamLibrary\steamapps\common\Crusader Kings III\game")

save = sf.read_save(SAVE)
res = {r.id: r for r in R.run_rules(save, R.select("all,R14,R15,R16", include_off=("R7",)),
                                    R.RuleContext(game_dir=GAME, reference=REF))}
ex = res["R17"].extra
print("attached", len(ex["attached"]), "independent", len(ex["attach_independent"]),
      "skipped", len(ex["attach_skipped"]), "contracts created", ex.get("contracts_created"))
for r in ex["attached"]:
    if any(t.startswith(("d_et_", "d_nf_")) for t in r["titles"]) and "--seats" in sys.argv \
            or not any(t.startswith(("d_et_", "d_nf_")) for t in r["titles"]):
        print("ATTACHED", json.dumps(r, default=str))
for r in ex["attach_skipped"]:
    print("SKIPPED ", json.dumps(r, default=str))
for r in ex["attach_independent"]:
    print("INDEP   ", json.dumps(r, default=str))
print("lock_step", json.dumps(res["R17"].extra.get("lock_step") or {}, default=str)[:600])
