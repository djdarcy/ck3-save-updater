"""``soak``, tested without ever starting a game or touching a real player's folder.

Every way out to the machine is replaced before each test: the process launch (``soak.Popen``), every window
function, the DPI call, the running-game check and the clock. By default each replacement RAISES when called, so a
test that expects a refusal cannot launch anything even if the refusal were missing; a test that runs the soak
installs a fake game in their place. The documents folder, the install folder, the run folder and HOME are all in
``tmp_path``.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from ck3_save_migrator import cli
from ck3_save_migrator import soak as sk

ROOT = Path(__file__).resolve().parents[1]
DLC = b'{ "enabled_mods" : [ "mod/mine.mod" ],\n  "disabled_dlcs": [] }\n'      # odd spacing: byte-exact restore


class Forbidden:
    def __init__(self, name):
        self.name = name

    def __call__(self, *a, **k):
        raise AssertionError(f"{self.name} was called; this test must not reach it")


@pytest.fixture
def world(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    for var in ("HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA"):
        monkeypatch.setenv(var, str(home))
    monkeypatch.setenv("XDG_CACHE_HOME", str(home / ".cache"))
    monkeypatch.setenv("CK3SM_SOAK_DIR", str(tmp_path / "soakbase"))
    docs = tmp_path / "docs"
    (docs / "save games").mkdir(parents=True)
    (docs / "logs").mkdir()
    (docs / "mod").mkdir()
    (docs / "mod" / "extra.mod").write_text('name="extra"\n', encoding="utf-8")
    (docs / "save games" / "autosave.ck3").write_bytes(b"the player's autosave")
    (docs / "save games" / "autosave_1.ck3").write_bytes(b"an older autosave")
    (docs / "save games" / "My_Campaign.ck3").write_bytes(b"a save the soak must not touch")
    (docs / "dlc_load.json").write_bytes(DLC)
    install = tmp_path / "install"
    (install / "binaries").mkdir(parents=True)
    (install / "binaries" / "ck3.exe").write_bytes(b"not a game")
    save = tmp_path / "Migrated.ck3"
    save.write_bytes(b"the migrated save")
    for name in ("Popen", "find_main_window", "send_to_back", "post_key", "click_client", "post_close",
                 "date_signature", "dpi_aware", "game_running"):
        monkeypatch.setattr(sk, name, Forbidden(name))
    clock = [1000.0]
    monkeypatch.setattr(sk, "now", lambda: clock[0])
    monkeypatch.setattr(sk, "sleep", lambda s: clock.__setitem__(0, clock[0] + s))
    return {"docs": docs, "install": install, "save": save, "home": home, "base": tmp_path / "soakbase",
            "clock": clock, "tmp": tmp_path}


def snapshot(folder: Path) -> dict:
    return {p.relative_to(folder).as_posix(): p.read_bytes() for p in sorted(folder.rglob("*")) if p.is_file()}


class FakeGame:
    """Stands in for ck3.exe. ``script`` decides what happens: "clean" (in game, then exits after Exit to Desktop),
    "crash-running" (crashes while running), "crash-exit" (crashes after the close), "no-load" (load fails), "hang"
    (never exits). While running it rewrites an autosave, writes a new one and changes dlc_load.json, as the game
    may."""

    def __init__(self, world, script, monkeypatch, date=None):
        self.w, self.script = world, script
        self.calls, self.keys, self.closed, self.clicks, self.cmd = 0, [], False, [], None
        self.rc = None
        self.pid = 4242
        self.dlc_at_launch = None
        self.staged_at_launch = None
        self.date = date or (lambda n: bytes([n % 256]) * 16)      # a moving date unless told otherwise
        monkeypatch.setattr(sk, "Popen", self.popen)
        monkeypatch.setattr(sk, "find_main_window", lambda pid: 0x1234 if pid == self.pid else 0)
        monkeypatch.setattr(sk, "send_to_back", lambda h: None)
        monkeypatch.setattr(sk, "post_key", lambda h, k: self.keys.append(k))
        monkeypatch.setattr(sk, "post_close", self.close)
        monkeypatch.setattr(sk, "click_client", lambda h, fx, fy, real=False: self.clicks.append(real) or "clicked")
        monkeypatch.setattr(sk, "date_signature", lambda h: self.date(self.calls))
        monkeypatch.setattr(sk, "dpi_aware", lambda: None)
        monkeypatch.setattr(sk, "game_running", lambda: False)

    def popen(self, cmd, cwd=None):
        self.cmd = cmd
        docs = self.w["docs"]
        self.dlc_at_launch = (docs / "dlc_load.json").read_bytes() if (docs / "dlc_load.json").exists() else None
        self.staged_at_launch = sorted(p.name for p in (docs / "save games").glob("MIGRATE_TEST__*"))
        return self

    def close(self, hwnd):
        self.closed = True

    def terminate(self):
        self.rc = -15

    def _crash(self, text):
        d = self.w["docs"] / "crashes" / "ck3_20261028_120000"
        d.mkdir(parents=True)
        (d / "exception.txt").write_text(text, encoding="utf-8")

    def poll(self):
        if self.rc is not None:
            return self.rc
        self.calls += 1
        docs = self.w["docs"]
        if self.calls == 1:
            if self.script == "no-load":
                (docs / "logs" / "error.log").write_text("[E] Could not load save game\n", encoding="utf-8")
                return None
            (docs / "logs" / "game.log").write_text("Setting idler 'In Game'\n", encoding="utf-8")
            (docs / "save games" / "autosave.ck3").write_bytes(b"the game's yearly autosave")
            (docs / "save games" / "autosave_2.ck3").write_bytes(b"a new autosave the game made")
            (docs / "dlc_load.json").write_bytes(b'{"enabled_mods":[]}')
        if self.script == "crash-running" and self.calls == 12:
            self._crash("\nUnhandled exception: ACCESS_VIOLATION in pdx::Simulation\n")
            self.rc = 1
            return self.rc
        if self.closed and self.clicks and self.script in ("clean", "crash-exit"):
            if self.script == "crash-exit":
                self._crash("Exception during shutdown: heap corruption\n")
            self.rc = 0
            return self.rc
        return None


def run(world, **kw):
    kw.setdefault("exit_after", 60)
    return sk.soak(world["save"], install=world["install"], docs=world["docs"], **kw, say=lambda m: None)


def assert_put_back(world):
    games = world["docs"] / "save games"
    assert (games / "autosave.ck3").read_bytes() == b"the player's autosave"
    assert (games / "autosave_1.ck3").read_bytes() == b"an older autosave"
    assert not (games / "autosave_2.ck3").exists()                         # the game's new one: moved out
    assert (games / "My_Campaign.ck3").read_bytes() == b"a save the soak must not touch"
    assert not list(games.glob("MIGRATE_TEST__*"))
    assert (world["docs"] / "dlc_load.json").read_bytes() == DLC
    assert not (world["base"] / "soak.lock").exists()


# --------------------------------------------------------------------------- runs
def test_a_clean_run_stages_launches_presses_exits_and_puts_everything_back(world, monkeypatch):
    game = FakeGame(world, "clean", monkeypatch)
    res = run(world, speed=3, run_dir=world["tmp"] / "run")
    assert res.outcome == "clean exit" and res.ok
    assert game.cmd[1:] == ["-gdpr-compliant", "-debug_mode", "-loadsave=MIGRATE_TEST__Migrated.ck3"]
    assert game.staged_at_launch == ["MIGRATE_TEST__Migrated.ck3"]
    assert game.keys[:2] == ["space", "3"] and game.closed and game.clicks == [False]
    assert_put_back(world)
    run_dir = world["tmp"] / "run"
    assert (run_dir / "autosave_2.ck3").read_bytes() == b"a new autosave the game made"
    assert (run_dir / "soak__autosave.ck3").read_bytes() == b"the game's yearly autosave"
    assert [c for c, ok in res.checks] == ["autosave autosave.ck3", "autosave autosave_1.ck3", "dlc_load.json"]


def test_a_crash_while_running_is_reported_and_everything_is_still_put_back(world, monkeypatch):
    FakeGame(world, "crash-running", monkeypatch)
    res = run(world)
    assert res.outcome == "crash while running"
    assert res.detail == "Unhandled exception: ACCESS_VIOLATION in pdx::Simulation"
    assert all(ok for _, ok in res.checks)
    assert_put_back(world)
    assert (res.run_dir / "crashes" / "ck3_20261028_120000" / "exception.txt").is_file()


def test_a_crash_on_exit_names_the_exception_line(world, monkeypatch):
    FakeGame(world, "crash-exit", monkeypatch)
    res = run(world)
    assert (res.outcome, res.detail) == ("crash on exit", "Exception during shutdown: heap corruption")
    assert_put_back(world)


def test_a_save_that_does_not_load(world, monkeypatch):
    FakeGame(world, "no-load", monkeypatch)
    res = run(world)
    assert res.outcome == "did not load" and "Could not load save game" in res.detail
    assert_put_back(world)


def test_a_game_that_does_not_exit_is_stopped_and_put_back(world, monkeypatch):
    game = FakeGame(world, "hang", monkeypatch)
    res = run(world)
    assert res.outcome == "did not exit" and game.rc == -15 and game.clicks == [False, True]
    assert_put_back(world)


def test_an_exception_inside_the_run_still_puts_everything_back(world, monkeypatch):
    game = FakeGame(world, "clean", monkeypatch)

    def boom(h, k):
        raise RuntimeError("the window went away")
    monkeypatch.setattr(sk, "post_key", boom)
    with pytest.raises(RuntimeError, match="window went away"):
        run(world)
    assert game.rc == -15
    assert_put_back(world)


def test_mods_are_enabled_for_the_run_only(world, monkeypatch):
    game = FakeGame(world, "clean", monkeypatch)
    run(world, mods=["mod/extra.mod"])
    assert json.loads(game.dlc_at_launch)["enabled_mods"] == ["mod/extra.mod"]
    assert (world["docs"] / "dlc_load.json").read_bytes() == DLC


def test_without_a_dlc_load_json_none_is_left_behind(world, monkeypatch):
    (world["docs"] / "dlc_load.json").unlink()
    game = FakeGame(world, "clean", monkeypatch)
    res = run(world, mods=["mod/extra.mod"])
    assert json.loads(game.dlc_at_launch)["enabled_mods"] == ["mod/extra.mod"]
    assert not (world["docs"] / "dlc_load.json").exists() and res.ok


def test_a_paused_game_gets_one_space(world, monkeypatch):
    game = FakeGame(world, "clean", monkeypatch, date=lambda n: b"\x10" * 16)      # the date never moves
    run(world, exit_after=60)
    assert game.keys[:2] == ["space", "5"] and game.keys[2:].count("space") == 1


def test_nothing_is_written_into_the_players_folders_but_what_is_put_back(world, monkeypatch):
    FakeGame(world, "clean", monkeypatch)
    before = snapshot(world["docs"])
    run(world)
    after = snapshot(world["docs"])
    new = set(after) - set(before)
    # the game's own logs are the game's; nothing else may be new, and every old file has its old bytes
    assert new <= {"logs/game.log", "logs/error.log"}, new
    assert {k: v for k, v in after.items() if k in before} == before
    assert not any(world["home"].rglob("*"))


# --------------------------------------------------------------------------- refusals: nothing launched, nothing changed
def refused(world, match, **kw):
    before = snapshot(world["docs"])
    with pytest.raises(sk.SoakRefused, match=match):
        run(world, **kw)
    assert snapshot(world["docs"]) == before
    if world["base"].exists():                       # no run folder was made (a lock file may be someone else's)
        assert [p.name for p in world["base"].iterdir()] in ([], ["soak.lock"])


def test_a_second_soak_is_refused_while_one_holds_the_lock(world):
    world["base"].mkdir()
    (world["base"] / "soak.lock").write_text("123\n", encoding="utf-8")
    refused(world, "another soak is running")
    assert (world["base"] / "soak.lock").read_text(encoding="utf-8") == "123\n"     # someone else's lock kept


def test_a_running_game_is_refused_and_the_lock_released(world, monkeypatch):
    monkeypatch.setattr(sk, "game_running", lambda: True)
    refused(world, "already running")
    assert not (world["base"] / "soak.lock").exists()


def test_a_different_file_in_the_staging_name_is_refused(world):
    (world["docs"] / "save games" / "MIGRATE_TEST__Migrated.ck3").write_bytes(b"someone else's")
    refused(world, "not overwriting it")


def test_an_unknown_mod_is_refused(world):
    refused(world, "no such mod descriptor", mods=["mod/nope.mod"])


def test_a_missing_game_is_refused(world):
    (world["install"] / "binaries" / "ck3.exe").unlink()
    refused(world, "no binaries/ck3.exe")


def test_a_bad_speed_is_refused(world):
    refused(world, "--speed is 1 to 5", speed=9)


# --------------------------------------------------------------------------- the command line
def test_the_command_exit_codes_and_report(world, monkeypatch, capsys):
    FakeGame(world, "crash-running", monkeypatch)
    code = cli.main(["soak", str(world["save"]), "--game", str(world["install"]), "--docs", str(world["docs"]),
                     "--exit-after", "60", "--run-dir", str(world["tmp"] / "run")])
    out = capsys.readouterr().out
    assert code == 6 and "soak: crash while running (Unhandled exception" in out
    assert "dlc_load.json: put back and verified" in out


def test_the_command_refuses_with_exit_2(world, monkeypatch, capsys):
    monkeypatch.setattr(sk, "game_running", lambda: True)
    code = cli.main(["soak", str(world["save"]), "--game", str(world["install"]), "--docs", str(world["docs"])])
    assert code == 2 and "soak refused: the game is already running" in capsys.readouterr().err


def test_the_command_says_it_starts_the_game_in_its_help(capsys):
    with pytest.raises(SystemExit):
        cli.main(["--help"])
    assert "START THE GAME" in capsys.readouterr().out


# --------------------------------------------------------------------------- copied, not rewritten
COPIED = ["find_main_window", "send_to_back", "KEYS", "post_key", "click_client", "EXIT_TO_DESKTOP", "tail_new",
          "WATCH"]


def _segment(src: str, name: str) -> str | None:
    for n in ast.parse(src).body:
        if isinstance(n, ast.FunctionDef) and n.name == name or \
                isinstance(n, ast.Assign) and any(getattr(t, "id", None) == name for t in n.targets):
            return ast.get_source_segment(src, n)
    return None


@pytest.mark.parametrize("name", COPIED)
def test_the_harness_functions_are_copied_unchanged(name):
    harness = (ROOT / "tests" / "one-offs" / "launch_load_test.py").read_text(encoding="utf-8")
    mine = (ROOT / "ck3_save_migrator" / "soak.py").read_text(encoding="utf-8")
    assert _segment(harness, name) is not None and _segment(harness, name) == _segment(mine, name)
