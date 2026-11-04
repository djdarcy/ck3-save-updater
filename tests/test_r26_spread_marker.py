"""R26 spread-marker: in each culture, 1.8's exposure_marker becomes 1.20's spread_marker and exposure_type goes.

One save holds a culture with all three 1.8 fields, a culture without them, a culture 1.20 already wrote (spread_marker),
and the same key names outside culture_manager, which are never touched.
"""

from __future__ import annotations

from ck3_save_migrator import savefile as sf
from ck3_save_migrator.rules import REGISTRY, RuleContext
from tests.fixtures.make_ck3 import build_ck3

R26 = next(r for r in REGISTRY if r.id == "R26")
META = b'meta_data={\n\tsave_game_version=8\n\tversion="1.8.1"\n}\n'
BODY = (
    b"culture_manager={\n\tcultures={\n"
    b"\t\t0={\n\t\t\tname=\"greek\"\n\t\t\texposure_marker=\"innovation_quilted_armor\"\n"
    b"\t\t\tfascination_marker=\"innovation_currency_01\"\n\t\t\tculture_marker=186\n\t\t\texposure_type=realm\n"
    b"\t\t\thead=51696\n\t\t}\n"
    b"\t\t1={\n\t\t\tname=\"akan\"\n\t\t\tfascination_marker=\"innovation_bannus\"\n\t\t}\n"
    b"\t\t2={\n\t\t\tname=\"han\"\n\t\t\tspread_marker=innovation_catapult\n\t\t\tculture_marker=12\n\t\t}\n"
    b"\t}\n}\n"
    b"living={\n\t5={\n\t\texposure_marker=\"not_a_culture\"\n\t\texposure_type=realm\n\t}\n}\n"
)


def run(body=BODY):
    save = sf.parse_save(build_ck3(meta=META, body=body))
    res = R26.run(save, RuleContext())
    g = save.gamestate
    return g[g.index(b"culture_manager={"):], res


def test_the_marker_is_renamed_and_the_type_dropped():
    g, res = run()
    culture0 = g[:g.index(b"\t\t1={")]
    assert b'spread_marker="innovation_quilted_armor"' in culture0
    assert b"exposure_" not in culture0
    assert b"culture_marker=186" in culture0 and b'fascination_marker="innovation_currency_01"' in culture0
    assert (res.matched, res.edited) == (2, 2)


def test_cultures_without_the_old_fields_and_other_sections_are_untouched():
    g, _ = run()
    assert g[g.index(b"\t\t1={"):] == BODY[BODY.index(b"\t\t1={"):]


def test_running_twice_changes_nothing_more():
    save = sf.parse_save(build_ck3(meta=META, body=BODY))
    R26.run(save, RuleContext())
    once = save.gamestate
    res = R26.run(save, RuleContext())
    assert save.gamestate == once and res.edited == 0
