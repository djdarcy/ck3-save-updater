"""S2 look save: in artifact 2937 (owned by the player, 50822; it carries artifact_vassal_opinion_2_modifier, +2 with
all vassals), replace that bonus with the two base-game modifiers that sum to +2: hold_court_8010_vassal_modifier (+5)
and artifact_vassal_opinion_penalty_1_modifier (-3). djdarcy then looks at how the artifact's window shows it.
Usage: python -I s2_vassal_opinion_look.py <in.ck3> <out.ck3>"""
import sys

sys.path.insert(0, r"C:\code\ck3-save-migrator")
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator import savefile as sf  # noqa: E402

save = sf.read_save(sys.argv[1])
d = save.gamestate
art = {e.key: e for e in gs.iter_entries(d, *gs.locate(d, "artifacts/artifacts").body)}[b"2937"]
old = b"artifact_vassal_opinion_2_modifier"
i = d.index(old, art.body[0], art.body[1])
save.replace_range(i, i + len(old), b"hold_court_8010_vassal_modifier artifact_vassal_opinion_penalty_1_modifier")
sf.write_save(save, sys.argv[2])
print("written")
