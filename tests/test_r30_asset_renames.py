"""R30 asset-renames: file references 1.20 renamed (artifact icons, armour models, a coat-of-arms emblem) point at the
names the game ships, and only when the old file is gone and the new one exists."""

from __future__ import annotations

from ck3_save_migrator import savefile as sf
from ck3_save_migrator.rules import REGISTRY, RuleContext
from tests.fixtures.make_ck3 import build_ck3

R30 = next(r for r in REGISTRY if r.id == "R30")
META = b'meta_data={\n\tsave_game_version=8\n\tversion="1.8.1"\n}\n'
ARTIFACT = (b'artifacts={\n\tartifacts={\n\t\t93={\n\t\t\tvisuals={\n\t\t\t\ttype="excalibur"\n'
            b'\t\t\t\ticon="artefact_icons_unique_artifact_excalibur.dds"\n'
            b'\t\t\t\tasset="male_clothes_secular_mena_war_nobility_01_artifact_entity"\n\t\t\t}\n\t\t}\n\t}\n}\n'
            b'coat_of_arms={\n\tcoat_of_arms_manager_database={\n\t\t5={\n\t\t\tcolored_emblem={\n'
            b'\t\t\t\ttexture="ce_african_cross_NU.dds"\n\t\t\t}\n\t\t}\n\t}\n}\n')


def game(tmp_path, *, icon=True, model=True, emblem=True):
    g = tmp_path / "game"
    (g / "gfx" / "interface" / "icons").mkdir(parents=True)
    (g / "gfx" / "models").mkdir(parents=True)
    (g / "gfx" / "coat_of_arms").mkdir(parents=True)
    if icon:
        (g / "gfx" / "interface" / "icons" / "artifact_icons_unique_artifact_excalibur.dds").write_bytes(b"")
    if emblem:
        (g / "gfx" / "coat_of_arms" / "ce_african_cross_nu2.dds").write_bytes(b"")
    if model:
        (g / "gfx" / "models" / "x.asset").write_text(
            'entity = {\n\tname = "m_clothes_sec_mena_war_nob_01_artifact_entity"\n}\n', encoding="utf-8")
    return g


def run(g, body):
    save = sf.parse_save(build_ck3(meta=META, body=body))
    ctx = RuleContext()
    ctx.game_dir = g
    return save, R30.run(save, ctx)


def test_the_renamed_icon_model_and_emblem_are_pointed_at_their_new_names(tmp_path):
    save, res = run(game(tmp_path), ARTIFACT)
    g = save.gamestate
    assert b'icon="artifact_icons_unique_artifact_excalibur.dds"' in g
    assert b'asset="m_clothes_sec_mena_war_nob_01_artifact_entity"' in g
    assert b'texture="ce_african_cross_nu2.dds"' in g
    assert res.matched == 3


def test_a_reference_is_left_when_the_new_file_is_not_shipped(tmp_path):
    save, res = run(game(tmp_path, model=False), ARTIFACT)
    g = save.gamestate
    assert b'asset="male_clothes_secular_mena_war_nobility_01_artifact_entity"' in g and res.matched == 2
    assert any("no m_clothes_sec_mena" in k for k in res.extra["left"])


def test_a_save_without_old_names_is_untouched(tmp_path):
    body = b'artifacts={\n\tartifacts={\n\t\t1={\n\t\t\tvisuals={\n\t\t\t\ticon="artifact_icons_x.dds"\n\t\t\t}\n\t\t}\n\t}\n}\n'
    save, res = run(game(tmp_path), body)
    assert res.matched == 0 and b'icon="artifact_icons_x.dds"' in save.gamestate
