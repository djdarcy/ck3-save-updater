"""R25 successor-keys: map keys the target game no longer defines to their successors, in the field that holds them.

A tiny 1.20 game folder defines the successors (``erudite_perk``, ``order_serjeants``, one tier of the artifact
phase-duration family); one save holds each case: a perk list, a list that already has the successor, both regiment
shapes (``regiments`` with chunks, hired ``army_regiments``), an artifact's modifier list with a tier that has a
successor and one that has none, and the same keys outside their fields (a flag, a description, a longer key), which
are never touched.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ck3_save_migrator import detect as D
from ck3_save_migrator import savefile as sf
from ck3_save_migrator.rules import REGISTRY, RuleContext
from ck3_save_migrator.rules.to_1_20 import SUCCESSORS
from tests.fixtures.make_ck3 import build_ck3

R25 = next(r for r in REGISTRY if r.id == "R25")
META = b'meta_data={\n\tsave_game_version=8\n\tversion="1.8.1"\n}\n'


def define(root: Path, folder: str, *keys: str) -> None:
    f = root / "common" / folder / "00_defs.txt"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("".join(f"{k} = {{\n\tx = 1\n}}\n" for k in keys), encoding="utf-8-sig")


@pytest.fixture
def game(tmp_path):
    g = tmp_path / "Crusader Kings III" / "game"
    define(g, "lifestyle_perks", "erudite_perk", "faithful_perk")
    define(g, "men_at_arms_types", "order_serjeants", "bowmen")
    define(g, "modifiers", "artifact_seduce_scheme_phase_duration_add_1_modifier", "artifact_placeholder_modifier")
    return g


BODY = (
    "living={\n"
    "1={\n\tfirst_name=\"Una\"\n\tperk={ faithful_perk scholar_perk pedagogy_perk }\n"
    "\tflag=scholar_perk\n}\n"
    "2={\n\tfirst_name=\"Dua\"\n\tperk={ scholar_perk erudite_perk }\n}\n"
    "}\n"
    "armies={\n\tregiments={\n"
    "\t\t16787471={\n\t\t\ttype=\"teutonic_knights\"\n\t\t\tmax=200\n\t\t}\n"
    "\t\t16787472={\n\t\t\ttype=\"teutonic_knights_of_a_mod\"\n\t\t\tmax=200\n\t\t}\n"
    "\t}\n\tarmy_regiments={\n"
    "\t\t33566215={\n\t\t\ttype=\"teutonic_knights\"\n\t\t\tsize=300\n\t\t\tsource=hired\n\t\t}\n"
    "\t\t12284={\n\t\t\ttype=\"bowmen\"\n\t\t\tsize=300\n\t\t}\n"
    "\t}\n}\n"
    "artifacts={\n\tartifacts={\n"
    "\t\t5={\n\t\t\tdescription=\"a scholar_perk and teutonic_knights in prose\"\n"
    "\t\t\tmodifiers={ artifact_placeholder_modifier artifact_seduce_scheme_power_add_1_modifier "
    "artifact_seduce_scheme_power_add_9_modifier }\n\t\t}\n"
    "\t}\n}\n"
).encode("utf-8")


def run(game, body=BODY, mod_dirs=()):
    save = sf.parse_save(build_ck3(meta=META, body=body))
    res = R25.run(save, RuleContext(game_dir=game, mod_dirs=list(mod_dirs)))
    return save.gamestate, res


def body(g: bytes) -> bytes:
    """The gamestate after its meta_data block: the part BODY wrote."""
    return g[g.index(b"living={"):]


def test_each_key_takes_its_successor_in_its_field(game):
    g, _ = run(game)
    assert b"perk={ faithful_perk erudite_perk pedagogy_perk }" in g
    assert g.count(b'type="order_serjeants"') == 2                      # a regiment and a hired regiment
    assert b"modifiers={ artifact_placeholder_modifier artifact_seduce_scheme_phase_duration_add_1_modifier " in g


def test_a_list_that_already_holds_the_successor_loses_the_old_key(game):
    g, res = run(game)
    assert b"perk={ erudite_perk }" in g
    assert res.extra["dropped_duplicates"] == {"scholar_perk -> erudite_perk": 1}


def test_the_same_words_outside_their_field_are_untouched(game):
    g, _ = run(game)
    assert b"\tflag=scholar_perk\n" in g
    assert b'description="a scholar_perk and teutonic_knights in prose"' in g
    assert b'type="teutonic_knights_of_a_mod"' in g


def test_a_key_whose_successor_the_game_does_not_define_stays_and_is_reported(game):
    g, res = run(game)
    assert b" artifact_seduce_scheme_power_add_9_modifier }" in g
    assert res.extra["left"] == {"artifact_seduce_scheme_power_add_9_modifier: no "
                                 "artifact_seduce_scheme_phase_duration_add_9_modifier defined": 1}


def test_a_key_a_listed_mod_still_defines_is_left_as_it_is(game, tmp_path):
    mod = tmp_path / "mods" / "123"
    define(mod, "men_at_arms_types", "teutonic_knights")
    g, res = run(game, mod_dirs=[mod])
    assert g.count(b'type="teutonic_knights"') == 2 and b"order_serjeants" not in g
    assert res.extra["left"]["teutonic_knights: still defined"] == 2


def test_the_counts(game):
    _, res = run(game)
    assert res.matched == 5 and res.edited == 5
    assert res.extra["mapped"] == {"teutonic_knights -> order_serjeants": 2, "scholar_perk -> erudite_perk": 1,
                                   "artifact_seduce_scheme_power_add_1_modifier -> "
                                   "artifact_seduce_scheme_phase_duration_add_1_modifier": 1}


def test_only_the_mapped_bytes_change(game):
    g, _ = run(game)
    assert body(g) == BODY.replace(b"faithful_perk scholar_perk", b"faithful_perk erudite_perk") \
        .replace(b"{ scholar_perk erudite_perk }", b"{ erudite_perk }") \
        .replace(b'type="teutonic_knights"\n', b'type="order_serjeants"\n') \
        .replace(b"artifact_seduce_scheme_power_add_1_modifier", b"artifact_seduce_scheme_phase_duration_add_1_modifier")


def test_without_the_game_folder_nothing_changes(tmp_path):
    g, res = run(None)
    assert body(g) == BODY and res.edited == 0 and "skipped" in res.extra


def test_teutonic_knights_become_order_serjeants():
    """djdarcy's correction (2026-11-04): matched on what the regiment is (holy-order heavy infantry, 36/26 against
    36/24), not on the name, which had pointed at order_knights."""
    row = next(r for r in SUCCESSORS if r.old == "teutonic_knights")
    assert (row.kind, row.field, row.new) == ("men-at-arms", "type", "order_serjeants")


def test_a_timed_modifier_takes_its_respelled_name(tmp_path):
    """1.20 corrected Quarysh to Quraysh in the Hawk of Quraysh modifiers (the same definitions, 1.8.2 and 1.20.1.2
    03_dlc_fp2_modifiers.txt); a character's timed modifier={ modifier="..." } keeps its effect."""
    g = tmp_path / "game"
    define(g, "modifiers", "fp2_hawk_of_quraysh_martial_modifier")
    body = (b"living={\n1={\n\tmodifier={\n\t\tmodifier=\"fp2_hawk_of_quarysh_martial_modifier\"\n"
            b"\t\texpiration_date=995.12.1\n\t}\n}\n}\n")
    out, res = run(g, body)
    assert b'modifier="fp2_hawk_of_quraysh_martial_modifier"' in out and b"quarysh" not in out
    assert res.extra["mapped"] == {"fp2_hawk_of_quarysh_martial_modifier -> fp2_hawk_of_quraysh_martial_modifier": 1}


def test_a_county_modifier_follows_its_event_to_the_new_name(tmp_path):
    """fp2_yearly.3000 gave rice_fields_modifier until 1.17 and terraced_hills_modifier from 1.18, with the same
    effect; a county's timed modifier takes the new name."""
    g = tmp_path / "game"
    define(g, "modifiers", "terraced_hills_modifier")
    body = (b"titles={\n\tlanded_titles={\n\t\t5={\n\t\t\tmodifier={\n\t\t\t\tmodifier=\"rice_fields_modifier\"\n"
            b"\t\t\t\texpiration_date=1001.9.7\n\t\t\t}\n\t\t}\n\t}\n}\n")
    out, res = run(g, body)
    assert b'modifier="terraced_hills_modifier"' in out and b"rice_fields" not in out
    assert res.extra["mapped"] == {"rice_fields_modifier -> terraced_hills_modifier": 1}


def test_djdarcys_answered_rows():
    """HOLD 18:05 (2026-11-04): each pinned to its successor, field and kind."""
    rows = {r.old: r for r in SUCCESSORS}
    assert (rows["chu_ko_nu"].new, rows["chu_ko_nu"].field) == ("shenbigong", "type")
    assert (rows["innovation_bombard"].new, rows["innovation_bombard"].field) == ("innovation_gunpowder", "type")
    assert (rows["medium_animal_hide"].new, rows["medium_animal_hide"].folder) == ("large_animal_hide", "artifacts/visuals")


def test_an_artifact_bonus_step_1_20_dropped_takes_the_nearest_kept_step(tmp_path):
    g = tmp_path / "game"
    define(g, "modifiers", "artifact_build_gold_cost_4_modifier", "artifact_vassal_tax_contribution_mult_2_modifier")
    body = (b"artifacts={\n\tartifacts={\n\t\t5={\n\t\t\tmodifiers={ artifact_build_gold_cost_7_modifier "
            b"artifact_vassal_tax_contribution_mult_1_modifier }\n\t\t}\n\t}\n}\n")
    out, res = run(g, body)
    assert b"modifiers={ artifact_build_gold_cost_4_modifier artifact_vassal_tax_contribution_mult_2_modifier }" in out
    assert res.edited == 2


def test_an_innovation_and_an_artifact_look_in_their_type_fields(tmp_path):
    g = tmp_path / "game"
    define(g, "culture/innovations", "innovation_gunpowder")
    define(g, "artifacts/visuals", "large_animal_hide")
    body = (b"culture_manager={\n\tcultures={\n\t\t0={\n\t\t\tculture_innovation={ {\n\t\t\t\t\ttype=\"innovation_bombard\"\n"
            b"\t\t\t\t}\n }\n\t\t}\n\t}\n}\nartifacts={\n\tartifacts={\n\t\t5={\n\t\t\tvisuals={\n"
            b"\t\t\t\ttype=\"medium_animal_hide\"\n\t\t\t}\n\t\t}\n\t}\n}\n")
    out, res = run(g, body)
    assert b'type="innovation_gunpowder"' in out and b'type="large_animal_hide"' in out and res.edited == 2


def test_the_all_vassal_opinion_bonus_stays_universal(tmp_path):
    """Item 6 (goal S2): +3 and +4 become +5 with all vassals, +1 stays +1 with all vassals."""
    g = tmp_path / "game"
    define(g, "modifiers", "hold_court_8010_vassal_modifier", "unity_harmonious_placation_modifier")
    body = (b"artifacts={\n\tartifacts={\n\t\t5={\n\t\t\tmodifiers={ artifact_vassal_opinion_4_modifier "
            b"artifact_vassal_opinion_1_modifier artifact_vassal_opinion_3_modifier }\n\t\t}\n\t}\n}\n")
    out, res = run(g, body)
    assert (b"modifiers={ hold_court_8010_vassal_modifier unity_harmonious_placation_modifier "
            b"hold_court_8010_vassal_modifier }") in out
    assert res.edited == 3


def test_every_row_cites_how_it_was_matched_and_on_what():
    assert all(r.how and r.source and r.folder for r in SUCCESSORS)


def test_the_detector_counts_what_r25_maps_and_nothing_on_its_output(game):
    save = sf.parse_save(build_ck3(meta=META, body=BODY))
    env = D.Env(game_dir=game)
    d = D.detect("R25", save.gamestate, env)
    assert d.state == "needed" and d.count == 5
    assert d.left == ["1 key left as it is (artifact_seduce_scheme_power_add_9_modifier: no "
                      "artifact_seduce_scheme_phase_duration_add_9_modifier defined)"]
    R25.run(save, RuleContext(game_dir=game))
    after = D.detect("R25", save.gamestate, D.Env(game_dir=game))
    assert after.state == "done" and after.left == d.left
    assert D.detect("R25", BODY, D.Env()).line() == "unknown: needs the game folder (its definitions)"
