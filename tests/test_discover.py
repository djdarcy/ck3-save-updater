"""Finding the game and the saves on any machine (ck3_save_migrator/discover.py), and the version checks.

Nothing here reads the real registry or disks: every Steam root, library, drive, home and current folder is a
temporary folder, and the registry is a dict. The Steam files are written as Steam writes them (tabs, doubled
backslashes in paths, the current and the older libraryfolders.vdf layouts)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from ck3_save_migrator import cli
from ck3_save_migrator import discover as D
from tests.fixtures.make_ck3 import build_ck3, make_game_dir
from tests.fixtures.religion import OLD_BODY, OLD_META, REF_BODY, REF_META

ROOT = Path(__file__).resolve().parents[1]
APP = D.CK3_APP_ID


# --------------------------------------------------------------------------- building Steam folders
def vdf_path(p: Path) -> str:
    """A path as libraryfolders.vdf writes it: backslashes doubled."""
    return str(p).replace("\\", "\\\\")


def install(library: Path, version: str | None, installdir: str = "Crusader Kings III", manifest: bool = True) -> Path:
    """CK3 in a Steam library: the game folder, the launcher settings (when ``version``), the app manifest."""
    game = make_game_dir(library / "steamapps" / "common" / installdir / "game")
    if version is not None:
        settings = game.parent / "launcher" / "launcher-settings.json"
        settings.parent.mkdir(parents=True, exist_ok=True)
        settings.write_text(json.dumps({"gameId": "ck3", "version": f"{version} (Crozier)", "rawVersion": version}))
    if manifest:
        (library / "steamapps" / f"appmanifest_{APP}.acf").write_text(
            f'"AppState"\n{{\n\t"appid"\t\t"{APP}"\n\t"name"\t\t"Crusader Kings III"\n'
            f'\t"installdir"\t\t"{installdir}"\n}}\n')
    return game


def steam_root(root: Path, libraries: list[tuple[Path, list[str]]], old_layout: bool = False) -> Path:
    """A Steam root whose libraryfolders.vdf lists itself and ``libraries`` ((path, app ids)), with a comment."""
    (root / "steamapps").mkdir(parents=True, exist_ok=True)
    entries = [(root, ["228980"])] + libraries
    if old_layout:
        body = "".join(f'\t"{i}"\t\t"{vdf_path(p)}"\n' for i, (p, _) in enumerate(entries))
        text = f'"LibraryFolders"\n{{\n\t"TimeNextStatsReport"\t\t"1700000000"\n{body}}}\n'
    else:
        body = "".join(
            f'\t"{i}"\n\t{{\n\t\t"path"\t\t"{vdf_path(p)}"\n\t\t"label"\t\t""\n\t\t"contentid"\t\t"6177"\n'
            f'\t\t"totalsize"\t\t"0"\n\t\t"apps"\n\t\t{{\n'
            + "".join(f'\t\t\t"{a}"\t\t"123456"\n' for a in apps) + "\t\t}\n\t}\n"
            for i, (p, apps) in enumerate(entries))
        text = f'// written by Steam\n"libraryfolders"\n{{\n{body}}}\n'
    (root / "steamapps" / "libraryfolders.vdf").write_text(text)
    return root


def find(tmp_path, **kw):
    """discover_games on a machine made of temporary folders: no registry, no drives, nothing at home."""
    home, cwd = tmp_path / "home", tmp_path / "cwd"
    home.mkdir(exist_ok=True)
    cwd.mkdir(exist_ok=True)
    args = {"env": "", "registry": {}, "drives": [], "home": home, "cwd": cwd, "system": "linux", **kw}
    return D.discover_games(**args)


# --------------------------------------------------------------------------- Steam's own record
def test_the_registry_leads_to_the_library_that_names_the_game(tmp_path):
    lib = tmp_path / "E_SteamLibrary"
    game = install(lib, "1.20.1.2")
    root = steam_root(tmp_path / "Steam", [(lib, ["1158310", "394360"])])
    found = find(tmp_path, registry={D.REG_STEAM_PATHS[0]: str(root)})
    assert [(g.path, g.version) for g in found] == [(game, "1.20.1.2")]
    assert "SteamPath in the registry" in found[0].source and "names the game" in found[0].source
    assert found[0].install == game.parent


def test_the_machine_wide_registry_value_is_read_when_the_users_is_missing(tmp_path):
    lib = tmp_path / "lib"
    game = install(lib, "1.20.1.2")
    root = steam_root(tmp_path / "Steam", [(lib, [APP])])
    found = find(tmp_path, registry={D.REG_STEAM_PATHS[1]: str(root)})
    assert [g.path for g in found] == [game] and "InstallPath" in found[0].source


def test_the_older_libraryfolders_layout_is_read(tmp_path):
    lib = tmp_path / "D_SteamLibrary"
    game = install(lib, "1.20.1.2")
    root = steam_root(tmp_path / "Steam", [(lib, [])], old_layout=True)
    assert [g.path for g in find(tmp_path, registry={D.REG_STEAM_PATHS[0]: str(root)})] == [game]


def test_a_library_with_the_manifest_but_no_apps_entry_is_found(tmp_path):
    lib = tmp_path / "lib"
    game = install(lib, "1.20.1.2")
    root = steam_root(tmp_path / "Steam", [(lib, [])])               # its apps block does not name CK3
    found = find(tmp_path, registry={D.REG_STEAM_PATHS[0]: str(root)})
    assert [g.path for g in found] == [game] and "found by its folders" in found[0].source


def test_the_manifests_installdir_is_followed(tmp_path):
    lib = tmp_path / "lib"
    game = install(lib, "1.20.1.2", installdir="CK3 Elsewhere")
    root = steam_root(tmp_path / "Steam", [(lib, [APP])])
    assert [g.path for g in find(tmp_path, registry={D.REG_STEAM_PATHS[0]: str(root)})] == [game]


def test_a_default_steam_root_at_home_is_read(tmp_path):
    home = tmp_path / "home"
    lib = tmp_path / "games"
    game = install(lib, "1.20.1.2")
    steam_root(home / ".local" / "share" / "Steam", [(lib, [APP])])
    found = find(tmp_path)
    assert [g.path for g in found] == [game] and ".local/share/Steam" in found[0].source


def test_without_steam_a_library_at_a_drives_root_is_found_then_nothing(tmp_path):
    drive = tmp_path / "E_drive"
    game = install(drive / "SteamLibrary", "1.20.1.2", manifest=False)
    found = find(tmp_path, drives=[str(drive)])
    assert [g.path for g in found] == [game] and "on a drive" in found[0].source
    assert find(tmp_path, drives=[str(tmp_path / "empty_drive")]) == []


def test_the_current_folder_or_its_game_child(tmp_path):
    cwd = tmp_path / "cwd"
    game = make_game_dir(cwd / "game")
    assert [(g.path, g.source) for g in find(tmp_path)] == [(game, "the current folder")]
    assert [g.path for g in find(tmp_path, cwd=game)] == [game]


# --------------------------------------------------------------------------- several installs, repeats, versions
def test_two_installs_newest_first_and_an_unknown_version_last(tmp_path):
    old = install(tmp_path / "lib_old", "1.18.0")
    new = install(tmp_path / "lib_new", "1.20.1.2")
    unknown = install(tmp_path / "lib_unknown", None)
    root = steam_root(tmp_path / "Steam", [(tmp_path / "lib_unknown", [APP]), (tmp_path / "lib_old", [APP]),
                                           (tmp_path / "lib_new", [APP])])
    found = find(tmp_path, registry={D.REG_STEAM_PATHS[0]: str(root)})
    assert [(g.path, g.version) for g in found] == [(new, "1.20.1.2"), (old, "1.18.0"), (unknown, None)]


def test_one_install_reached_twice_is_listed_once_with_its_first_source(tmp_path):
    home = tmp_path / "home"
    lib = tmp_path / "lib"
    game = install(lib, "1.20.1.2")
    root = steam_root(home / ".steam" / "steam", [(lib, [APP])])
    found = find(tmp_path, registry={D.REG_STEAM_PATHS[0]: str(root)}, drives=[str(tmp_path)],
                 cwd=game)
    assert [g.path for g in found] == [game] and "registry" in found[0].source


def test_a_named_folder_is_used_alone_and_one_that_is_not_a_game_is_refused(tmp_path):
    game = make_game_dir(tmp_path / "mine" / "game")
    install(tmp_path / "lib", "1.20.1.2")
    assert [(g.path, g.source) for g in find(tmp_path, explicit=str(game))] == [(game, "--game-dir")]
    assert [g.source for g in find(tmp_path, env=str(game))] == ["$CK3_GAME_DIR"]
    assert find(tmp_path, env="none") == [] and find(tmp_path, explicit="none", env=str(game)) == []
    bad = tmp_path / "not_a_game"
    bad.mkdir()
    with pytest.raises(FileNotFoundError, match=r"CK3_GAME_DIR .*not_a_game.*common.landed_titles"):
        find(tmp_path, env=str(bad))


def test_the_version_comes_from_the_launcher_settings_or_is_unknown(tmp_path):
    game = install(tmp_path / "lib", "1.20.1.2")
    assert D.game_version(game) == "1.20.1.2"
    (game.parent / "launcher" / "launcher-settings.json").write_text("not json")
    assert D.game_version(game) is None
    assert D.game_version(tmp_path / "nowhere") is None


def test_compare_versions():
    assert D.compare_versions("1.20.1.2", "1.8.1") == 1
    assert D.compare_versions("1.8.1", "1.20.1.2") == -1
    assert D.compare_versions("1.20", "1.20.0.0") == 0
    assert D.compare_versions("1.20.1.2 (Crozier)", "1.20.1.2") == 0
    assert D.compare_versions(None, "1.20") is None and D.compare_versions("x", "1.20") is None


def test_parse_vdf_reads_blocks_strings_escapes_and_comments():
    text = ('"a" // a comment\n{\n\t"path"\t\t"C:\\\\Program Files (x86)\\\\Steam"\n\t"q"\t"say \\"hi\\""\n'
            '\t"apps"\n\t{\n\t\t"1158310"\t\t"9"\n\t}\n}\n')
    assert D.parse_vdf(text) == {"a": {"path": r"C:\Program Files (x86)\Steam", "q": 'say "hi"',
                                       "apps": {"1158310": "9"}}}
    assert D.parse_vdf('"a" { "b" "c"') == {"a": {"b": "c"}}          # unbalanced: what was read is kept


# --------------------------------------------------------------------------- the saves
def test_the_save_folder_on_each_system(tmp_path):
    home = tmp_path / "home"
    games = Path("Paradox Interactive") / "Crusader Kings III" / "save games"
    assert D.save_games_dir(system="linux", home=home) == home / ".local" / "share" / games
    assert D.save_games_dir(system="darwin", home=home) == home / "Documents" / games
    onedrive = tmp_path / "OneDrive" / "Documents"
    assert D.save_games_dir(system="win32", home=home, documents=onedrive) == onedrive / games


def test_on_windows_the_save_folder_is_never_guessed_from_home(tmp_path, monkeypatch):
    monkeypatch.setattr(D, "documents_dir", lambda: None)            # the known folder could not be read
    assert D.save_games_dir(system="win32", home=tmp_path) is None


def test_find_save_by_path_by_name_with_or_without_ck3(tmp_path):
    folder = tmp_path / "save games"
    folder.mkdir()
    (folder / "Brian_987.ck3").write_bytes(b"x")
    direct = tmp_path / "elsewhere.ck3"
    direct.write_bytes(b"x")
    assert D.find_save(str(direct), folder=folder) == direct
    assert D.find_save("Brian_987", folder=folder) == folder / "Brian_987.ck3"
    assert D.find_save("Brian_987.ck3", folder=folder) == folder / "Brian_987.ck3"
    assert D.find_save("brian_987", folder=folder) == folder / "Brian_987.ck3"


def test_find_save_not_found_and_ambiguous(tmp_path):
    folder = tmp_path / "save games"
    folder.mkdir()
    with pytest.raises(FileNotFoundError, match="Nobody.*not in"):
        D.find_save("Nobody", folder=folder)
    with pytest.raises(FileNotFoundError, match="no save folder"):
        D.find_save("Nobody", folder=tmp_path / "missing")
    (folder / "Twin.ck3").write_bytes(b"x")
    (folder / "twin.ck3").write_bytes(b"x")
    if len(list(folder.iterdir())) < 2:
        pytest.skip("this file system does not tell case apart")
    with pytest.raises(ValueError, match="more than one save.*Twin.ck3.*twin.ck3"):
        D.find_save("TWIN", folder=folder)


def test_a_save_name_works_on_the_command_line(tmp_path, monkeypatch, capsys):
    folder = tmp_path / "home" / ".local" / "share" / "Paradox Interactive" / "Crusader Kings III" / "save games"
    folder.mkdir(parents=True)
    (folder / "Brian_987.ck3").write_bytes(build_ck3(meta=OLD_META, body=OLD_BODY))
    monkeypatch.setattr(D.Path, "home", classmethod(lambda cls: tmp_path / "home"))
    monkeypatch.setattr(D.sys, "platform", "linux")
    monkeypatch.chdir(tmp_path)
    assert cli.main(["inspect", "Brian_987"]) == 0
    assert "Brian_987.ck3" in capsys.readouterr().out
    assert cli.main(["inspect", "Nobody"]) == 1
    assert "no such save: Nobody" in capsys.readouterr().err


# --------------------------------------------------------------------------- versions of the save, and migrate
def test_save_versions_on_both_measured_shapes():
    assert D.save_versions(OLD_META) == {"version": "1.8.1", "save_game_version": 8, "portraits_version": 3}
    assert D.save_versions(REF_META) == {"version": "1.20.1.2", "save_game_version": 18, "portraits_version": 5}
    assert D.save_versions(b"meta_data={\n}\n") == {"version": None, "save_game_version": None,
                                                    "portraits_version": None}


def game_with_version(tmp_path, version):
    game = make_game_dir(tmp_path / "CK3" / "game")
    if version:
        (game.parent / "launcher").mkdir()
        (game.parent / "launcher" / "launcher-settings.json").write_text(json.dumps({"rawVersion": version}))
    return game


def test_migrate_refuses_a_save_newer_than_the_game(tmp_path, capsys):
    game = game_with_version(tmp_path, "1.18.0")
    save = tmp_path / "new.ck3"
    save.write_bytes(build_ck3(meta=REF_META, body=REF_BODY))
    out = tmp_path / "out.ck3"
    code = cli.main(["migrate", str(save), "--game-dir", str(game), "--reference", "none", "--no-lint", "-o", str(out)])
    err = capsys.readouterr().err
    assert code == 1 and not out.exists()
    assert "1.20.1.2" in err and "1.18.0" in err and "newer than the game" in err


def test_migrate_goes_on_for_an_older_save_and_says_when_the_games_version_is_unknown(tmp_path, capsys):
    save = tmp_path / "old.ck3"
    save.write_bytes(build_ck3(meta=OLD_META, body=OLD_BODY))
    game = game_with_version(tmp_path, "1.20.1.2")
    args = ["migrate", str(save), "--reference", "none", "--no-lint", "--game-dir", str(game)]
    assert cli.main(args + ["-o", str(tmp_path / "a.ck3"), "--report", str(tmp_path / "a.json")]) == 0
    assert "version is unknown" not in capsys.readouterr().err
    rep = json.loads((tmp_path / "a.json").read_text(encoding="utf-8"))
    assert rep["game_installs"] == [{"source": "--game-dir", "path": str(game), "version": "1.20.1.2"}]
    assert rep["save_versions"] == {"version": "1.8.1", "save_game_version": 8, "portraits_version": 3}
    (game.parent / "launcher" / "launcher-settings.json").unlink()
    assert cli.main(args + ["-o", str(tmp_path / "b.ck3")]) == 0
    assert "the game's version is unknown" in capsys.readouterr().err


def test_inspect_prints_the_saves_versions_and_the_install_with_its_source(tmp_path, capsys):
    save = tmp_path / "old.ck3"
    save.write_bytes(build_ck3(meta=OLD_META, body=OLD_BODY))
    game = game_with_version(tmp_path, "1.20.1.2")
    assert cli.main(["inspect", str(save), "--game-dir", str(game)]) == 0
    out = capsys.readouterr().out
    assert "versions  : version 1.8.1, save_game_version 8, portraits_version 3" in out
    assert f"game      : 1.20.1.2  {game}  (from --game-dir)" in out


def test_inspect_lists_every_install_found(tmp_path, capsys, monkeypatch):
    new = install(tmp_path / "a" / "SteamLibrary", "1.20.1.2")
    old = install(tmp_path / "b" / "SteamLibrary", "1.18.0")
    found = find(tmp_path, drives=[str(tmp_path / "a"), str(tmp_path / "b")])
    assert [g.path for g in found] == [new, old]
    monkeypatch.setattr(cli, "game_installs", lambda explicit: found)
    save = tmp_path / "old.ck3"
    save.write_bytes(build_ck3(meta=OLD_META, body=OLD_BODY))
    assert cli.main(["inspect", str(save)]) == 0
    out = capsys.readouterr().out
    assert re.search(rf"game      : 1\.20\.1\.2  {re.escape(str(new))}  \(from .*a/SteamLibrary on a drive", out)
    assert re.search(rf"also      : 1\.18\.0  {re.escape(str(old))}  \(from .*\)  \(not used", out)


# --------------------------------------------------------------------------- nothing personal in the package
def test_no_game_path_of_one_machine_is_written_in_the_package():
    """No drive-lettered Steam library (the old E:\\SteamLibrary candidate) in the package's code; the drive scan
    builds <drive>:\\SteamLibrary from the drives that exist."""
    hits = []
    for f in (ROOT / "ck3_save_migrator").rglob("*.py"):
        for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"[A-Za-z]:(\\\\|\\|/)+SteamLibrary", line):
                hits.append(f"{f.name}:{n}")
    assert hits == []
    assert not hasattr(cli, "GAME_DIR_CANDIDATES")
