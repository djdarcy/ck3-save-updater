"""reference-mod polish (the patch-day goal, S5): the installed version in the descriptor and the text, shorter names,
and the bookmark's art copied from the player's install (measured on 1.21.0: without it the bookmark screen is white
and error.log reports the background and location image not found)."""

from __future__ import annotations

from pathlib import Path

import pytest

from ck3_save_migrator import refmod as M

ART = Path("gfx/interface/bookmarks")


def b(**kw):
    return M.make_bookmark(date="987.10.27", character=900, title="d_munster", culture="irish",
                           religion="insular_celtic", house="house_x", birth="941.1.1", **kw)


@pytest.fixture
def game(tmp_path):
    g = tmp_path / "game"
    (g / ART).mkdir(parents=True)
    (g / ART / M.ART_BACKGROUND).write_bytes(b"DDS background")
    (g / ART / M.ART_LOCATION).write_bytes(b"DDS location")
    return g


def test_the_installed_version_names_the_supported_version_and_the_description():
    m = b(game_version="1.21.0")
    assert 'supported_version="1.21.*"' in M.descriptor(m)
    assert "A plain 1.21 start on 987.10.27" in M.localization(m)
    assert 'supported_version="1.20.*"' in M.descriptor(b())          # no version known: the old default


def test_the_names_are_short_enough_for_the_tab():
    m = b()
    assert 'name="Ref Bookmark 987.10.27 (ck3update)"' in M.descriptor(m)
    assert f' {m.bookmark_key}: "Ref 987.10.27"' in M.localization(m)


def test_a_bad_version_is_refused():
    with pytest.raises(M.RefModError, match="not a version"):
        b(game_version="Florin")


def test_the_art_is_copied_from_the_install_under_the_names_the_game_looks_for(game, tmp_path):
    out = tmp_path / "mods"
    out.mkdir()
    m = b()
    written = M.write_mod(m, out, game_dir=game)
    bg = out / m.folder / ART / f"{m.bookmark_key}.dds"
    loc = out / m.folder / ART / f"{m.bookmark_key}_{m.character_key}.dds"
    assert bg in written and loc in written
    assert bg.read_bytes() == b"DDS background" and loc.read_bytes() == b"DDS location"


def test_without_the_game_or_its_pictures_there_is_no_art(game, tmp_path):
    out = tmp_path / "mods"
    out.mkdir()
    assert not [p for p in M.write_mod(b(), out) if p.suffix == ".dds"]
    (game / ART / M.ART_LOCATION).unlink()
    out2 = tmp_path / "mods2"
    out2.mkdir()
    assert not [p for p in M.write_mod(b(), out2, game_dir=game) if p.suffix == ".dds"]
