"""The reference-mod writer (refmod.py) and the `reference-mod` command."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from ck3_save_migrator import cli
from ck3_save_migrator import refmod as M

ROOT = Path(__file__).resolve().parents[1]
BRIAN = dict(date="987.10.27", character=900, title="d_munster", culture="irish", religion="insular_celtic",
             house="house_british_isles_briain", birth="941.1.1", name="Brian Boruma")
ARGS = ["--date", "987.10.27", "--character", "900", "--title", "d_munster", "--culture", "irish",
        "--religion", "insular_celtic", "--house", "house_british_isles_briain", "--birth", "941.1.1"]


@pytest.fixture
def b() -> M.Bookmark:
    return M.make_bookmark(**BRIAN)


# --------------------------------------------------------------------------- the texts
def test_the_bookmark_starts_on_the_date_with_the_characters_block(b):
    t = M.bookmark(b)
    assert t.count("bm_987_10_27 = {") == 1 and "\tstart_date = 987.10.27\n" in t
    for line in ("history_id = 900", "title = d_munster", "culture = irish", "religion = insular_celtic",
                 "government = feudal_government", "birth = 941.1.1", "type = male",
                 "dynasty_house = house_british_isles_briain", "dynasty_splendor_level = 1",
                 "name = bookmark_ref_987_10_27_900", 'difficulty = "BOOKMARK_CHARACTER_DIFFICULTY_MEDIUM"',
                 "position = { 400 300 }", "is_playable = yes", "value = 0"):
        assert f"\t{line}\n" in t, line
    assert t.count("{") == t.count("}")


def test_female_sets_the_type():
    assert "\t\ttype = female\n" in M.bookmark(M.make_bookmark(**{**BRIAN, "female": True}))


def test_the_localization_starts_with_a_bom_and_names_every_key(b):
    t = M.localization(b)
    assert t.startswith("﻿l_english:\n")
    for key in ("bm_987_10_27", "bm_987_10_27_desc", "bookmark_ref_987_10_27_900",
                "bookmark_ref_987_10_27_900_desc", "bookmark_ref_987_10_27_900_subheading"):
        assert f"\n {key}: \"" in t, key
    assert ' bookmark_ref_987_10_27_900: "Brian Boruma"\n' in t


def test_the_descriptor_and_the_launcher_mod(b, tmp_path):
    d = M.descriptor(b)
    assert 'name="Ref Bookmark 987.10.27 (ck3update)"' in d and 'supported_version="1.20.*"' in d
    assert '\t"Utilities"' in d
    folder = tmp_path / "zz_ref_987_10_27"
    m = M.launcher_mod(b, folder)
    assert m.startswith(d) and m.endswith(f'path="{folder.resolve().as_posix()}"\n')


def test_the_date_is_normalised_and_names_the_folder():
    b = M.make_bookmark(**{**BRIAN, "date": "0987.01.05", "birth": "941.01.01"})
    assert (b.date, b.birth, b.folder, b.bookmark_key) == ("987.1.5", "941.1.1", "zz_ref_987_1_5", "bm_987_1_5")


@pytest.mark.parametrize("date", ["987-10-27", "987.10", "987.13.1", "987.2.29", "987.4.31", "987.10.0",
                                  "year.1.1", ""])
def test_a_bad_date_is_refused(date):
    with pytest.raises(M.RefModError):
        M.parse_date(date)


@pytest.mark.parametrize("change", [{"character": "brian"}, {"title": "d munster"}, {"birth": "988.1.1"},
                                    {"name": 'Brian "Boru"'}, {"house": ""}])
def test_bad_options_are_refused(change):
    with pytest.raises(M.RefModError):
        M.make_bookmark(**{**BRIAN, **change})


# --------------------------------------------------------------------------- writing
def test_write_mod_writes_four_files_with_the_bom_on_disk(b, tmp_path):
    written = M.write_mod(b, tmp_path)
    rel = sorted(p.relative_to(tmp_path).as_posix() for p in written)
    assert rel == ["zz_ref_987_10_27.mod", "zz_ref_987_10_27/common/bookmarks/bookmarks/zz_ref.txt",
                   "zz_ref_987_10_27/descriptor.mod", "zz_ref_987_10_27/localization/english/zz_ref_l_english.yml"]
    yml = tmp_path / "zz_ref_987_10_27" / "localization" / "english" / "zz_ref_l_english.yml"
    assert yml.read_bytes().startswith(b"\xef\xbb\xbfl_english:")
    assert not (tmp_path / "zz_ref_987_10_27" / "descriptor.mod").read_bytes().startswith(b"\xef\xbb\xbf")


@pytest.mark.parametrize("existing", ["zz_ref_987_10_27", "zz_ref_987_10_27.mod"])
def test_an_existing_folder_or_mod_file_is_refused_and_nothing_is_written(b, tmp_path, existing):
    target = tmp_path / existing
    target.mkdir() if not existing.endswith(".mod") else target.write_text("mine", encoding="utf-8")
    before = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*"))
    with pytest.raises(M.RefModError, match="refusing to overwrite"):
        M.write_mod(b, tmp_path)
    assert sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*")) == before


def test_replace_writes_over_a_mod_this_command_wrote(b, tmp_path):
    # --force (djdarcy 2026-11-17): an earlier reference mod of the same date is written over, in place; a file the
    # old version wrote and the new one does not is left, not deleted
    M.write_mod(b, tmp_path)
    stale = tmp_path / b.folder / "leftover.txt"
    stale.write_text("old", encoding="utf-8")
    (tmp_path / b.folder / "descriptor.mod").write_text(
        'name="Reference bookmark 987.10.27 (ck3update)"\nsupported_version="1.20.*"\n', encoding="utf-8")
    written = M.write_mod(b, tmp_path, replace=True)
    assert (tmp_path / b.folder / "descriptor.mod") in written
    assert "Ref Bookmark" in (tmp_path / b.folder / "descriptor.mod").read_text(encoding="utf-8")
    assert stale.read_text(encoding="utf-8") == "old"


def _foreign(tmp_path, existing):
    target = tmp_path / existing
    if existing.endswith(".mod"):
        target.write_text('name="Somebody Else\'s Mod"\n', encoding="utf-8")
    else:
        target.mkdir()
        (target / "descriptor.mod").write_text('name="Somebody Else\'s Mod"\n', encoding="utf-8")
    return {p.relative_to(tmp_path).as_posix(): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}


def _files(tmp_path):
    return {p.relative_to(tmp_path).as_posix(): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}


@pytest.mark.parametrize("existing", ["zz_ref_987_10_27", "zz_ref_987_10_27.mod"])
def test_replace_without_a_terminal_refuses_a_mod_not_marked_as_ours(b, tmp_path, existing):
    # its name is the only evidence; with nobody to ask, --force is refused and the reason is said
    before = _foreign(tmp_path, existing)
    with pytest.raises(M.RefModError, match="no terminal to ask you from"):
        M.write_mod(b, tmp_path, replace=True)
    assert _files(tmp_path) == before


@pytest.mark.parametrize("existing", ["zz_ref_987_10_27", "zz_ref_987_10_27.mod"])
def test_replace_asks_about_a_mod_not_marked_as_ours(b, tmp_path, existing):
    # djdarcy 2026-11-17: "if we can't tell for certain we can just prompt with a Y/n"
    before = _foreign(tmp_path, existing)
    asked = []
    with pytest.raises(M.RefModError, match="you answered no"):
        M.write_mod(b, tmp_path, replace=True, confirm=lambda ps: asked.append(ps) or False)
    assert len(asked) == 1 and asked[0] == [tmp_path / existing] and _files(tmp_path) == before
    M.write_mod(b, tmp_path, replace=True, confirm=lambda ps: True)
    assert "Ref Bookmark" in (tmp_path / "zz_ref_987_10_27" / "descriptor.mod").read_text(encoding="utf-8")


def test_replace_does_not_ask_about_a_mod_marked_as_ours(b, tmp_path):
    M.write_mod(b, tmp_path)
    M.write_mod(b, tmp_path, replace=True, confirm=lambda ps: pytest.fail(f"asked about {ps}"))


def test_a_missing_output_folder_is_refused(b, tmp_path):
    with pytest.raises(M.RefModError, match="does not exist"):
        M.write_mod(b, tmp_path / "nope")


# --------------------------------------------------------------------------- the command
def test_the_command_writes_the_mod_and_prints_the_next_steps(tmp_path, capsys):
    assert cli.main(["reference-mod", *ARGS, "--out", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert (tmp_path / "zz_ref_987_10_27" / "common" / "bookmarks" / "bookmarks" / "zz_ref.txt").is_file()
    assert "enable the mod 'Ref Bookmark 987.10.27 (ck3update)'" in out       # the name the launcher shows
    assert "find that save by themselves" in out and "--reference" in out
    assert out.count("wrote: ") == 4


def test_without_out_the_mod_goes_to_the_games_own_mod_folder(tmp_path, monkeypatch, capsys):
    """The default --out (for the README's quick start). Both lookups point into tmp_path, so a broken default can
    never write into the real documents folder."""
    docs = tmp_path / "Crusader Kings III"
    (docs / "mod").mkdir(parents=True)
    monkeypatch.setattr(cli, "game_documents_dir", lambda: docs)
    monkeypatch.setattr("ck3_save_migrator.discover.documents_dir", lambda: tmp_path)
    assert cli.main(["reference-mod", *ARGS]) == 0
    assert (docs / "mod" / "zz_ref_987_10_27" / "descriptor.mod").is_file()
    assert (docs / "mod" / "zz_ref_987_10_27.mod").is_file()


def test_without_out_and_no_documents_folder_it_asks_for_out(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "game_documents_dir", lambda: None)
    monkeypatch.setattr("ck3_save_migrator.discover.documents_dir", lambda: tmp_path)
    assert cli.main(["reference-mod", *ARGS]) == 1
    assert "give --out" in capsys.readouterr().err


def test_the_command_refuses_a_second_run_with_exit_1_naming_the_path(tmp_path, capsys):
    assert cli.main(["reference-mod", *ARGS, "--out", str(tmp_path)]) == 0
    capsys.readouterr()
    assert cli.main(["reference-mod", *ARGS, "--out", str(tmp_path)]) == 1
    err = capsys.readouterr().err
    assert "refusing to overwrite" in err and "zz_ref_987_10_27" in err


def test_the_command_refuses_a_bad_date_with_exit_1(tmp_path, capsys):
    args = ["reference-mod", *ARGS, "--out", str(tmp_path)]
    args[args.index("987.10.27")] = "987.10.32"
    assert cli.main(args) == 1
    assert "day 32" in capsys.readouterr().err and not any(tmp_path.iterdir())


def test_the_command_round_trips_in_a_subprocess(tmp_path):
    r = subprocess.run([sys.executable, "-m", "ck3_save_migrator", "reference-mod", *ARGS, "--female",
                        "--name", "Test Ruler", "--out", str(tmp_path)],
                       capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stderr
    txt = (tmp_path / "zz_ref_987_10_27" / "common" / "bookmarks" / "bookmarks" / "zz_ref.txt").read_text()
    assert "type = female" in txt
    mod = (tmp_path / "zz_ref_987_10_27.mod").read_text(encoding="utf-8")
    assert f'path="{(tmp_path / "zz_ref_987_10_27").resolve().as_posix()}"' in mod
