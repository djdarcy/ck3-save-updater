"""U2: a record per save game (read back to pre-fill the next update) and --in-place with a backup.

Every file a test writes is under its own temporary folder; the config, and the record folder beside it, come from
CK3SM_CONFIG (conftest). Saves and games are tests/test_update.py's: a save's random_seed is the line random_seed=
in its gamestate, and two files with the same seed are two saves of one save game.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest

from ck3_save_migrator import cli, record
from ck3_save_migrator import userpacks as U
from tests import test_update as TU
from tests.test_update import OLD_BODY, OLD_META, build_ck3, flat, game, old_save, run

saves = TU.saves
no_reference_from_the_environment = TU.no_reference_from_the_environment

COPY_AND_WRITE = """import shutil, sys
from pathlib import Path
shutil.copyfile(sys.argv[1], sys.argv[2])
Path(sys.argv[4]).write_text(sys.argv[3], encoding="utf-8")
"""


def witness_pack(tmp_path) -> tuple[Path, Path]:
    """A run patch W1 needing witness, tools (a folder holding copy.py) and mark (the file it writes witness to)."""
    tools = tmp_path / "tools"
    tools.mkdir()
    (tools / "copy.py").write_text(COPY_AND_WRITE, encoding="utf-8")
    folder = U.packs_dir() / "witness"
    (folder / "W1-run").mkdir(parents=True)
    (folder / "pack.toml").write_text('format = 1\nid = "witness"\ntitle = "t"\norder = ["W1"]\n', encoding="utf-8")
    (folder / "W1-run" / "patch.toml").write_text(
        'format = 1\nid = "W1"\nname = "w1-run"\ntitle = "a program"\nsince = "1"\n\n[run]\n'
        'command = ["@@python@@", "@@tools@@/copy.py", "@@input@@", "@@output@@", "@@witness@@", "@@mark@@"]\n'
        'needs = { witness = "a word", tools = "the folder holding copy.py", mark = "the file to write it to" }\n',
        encoding="utf-8")
    mark = tmp_path / "mark.txt"
    mark.write_text("not yet", encoding="utf-8")
    return tools, mark


def update(capsys, save, g, *extra):
    return run(capsys, "update", str(save), "--game-dir", str(g), "--reference", "none", "--no-lint",
               "--allow-run", *extra)


# --------------------------------------------------------------------------- the record, keyed by the save game
def test_a_second_save_of_one_save_game_is_pre_filled_from_the_record(tmp_path, saves, capsys):
    tools, mark = witness_pack(tmp_path)
    g = game(tmp_path)
    first = old_save(saves, "Campaign.ck3")
    code, _, err = update(capsys, first, g, "--var", "witness=W1", "--var", f"tools={tools.as_posix()}",
                          "--var", f"mark={mark.as_posix()}")
    assert code == 0, err
    assert mark.read_text(encoding="utf-8") == "W1"
    mark.write_text("old", encoding="utf-8")
    later = old_save(saves, "Campaign_later.ck3")                  # the same random_seed, another file
    code, out, err = update(capsys, later, g)
    assert code == 0, err
    assert mark.read_text(encoding="utf-8") == "W1"                # the pre-filled witness reached the patch
    assert "pre-filled: --var witness=W1 (from the record of Campaign)" in flat(out)
    assert "status: Campaign: last updated" in out and "from Campaign.ck3 (1 update)" in flat(out)
    rec = record.read_record("111")
    assert rec["label"] == "Campaign" and len(rec["update"]) == 2
    row = rec["update"][1]
    assert row["input"].endswith("Campaign_later.ck3") and "--var witness=W1" in row["prefilled"]
    assert {"id": "W1", "pack": "witness"} in row["patches"] and {"id": "R7", "pack": "to_1_20"} in row["patches"]
    assert row["inputs"]["vars"]["witness"] == "W1" and "reference" not in json.dumps(row["inputs"])
    assert row["tool"].startswith("ck3-save-updater ") and row["game_version"] == "1.20.1.2"
    assert row["output_sha256"] and row["input_sha256"]


def test_a_save_of_another_save_game_gets_its_own_record_and_no_pre_fill(tmp_path, saves, capsys):
    tools, mark = witness_pack(tmp_path)
    g = game(tmp_path)
    update(capsys, old_save(saves), g, "--var", "witness=W1", "--var", f"tools={tools.as_posix()}",
           "--var", f"mark={mark.as_posix()}")
    other = saves / "Other.ck3"
    other.write_bytes(build_ck3(meta=OLD_META, body=OLD_BODY + b"random_seed=999\n"))
    code, out, _ = update(capsys, other, g)
    assert code == 0 and "pre-filled:" not in out and "status: none yet" in out
    assert "needs --var witness" in out
    assert sorted(p.name for p in record.games_dir().iterdir()) == ["111.toml", "999.toml"]


def test_a_recorded_folder_that_is_gone_is_not_used(tmp_path, saves, capsys):
    tools, mark = witness_pack(tmp_path)
    g = game(tmp_path)
    update(capsys, old_save(saves), g, "--var", "witness=W1", "--var", f"tools={tools.as_posix()}",
           "--var", f"mark={mark.as_posix()}")
    (tools / "copy.py").unlink()
    tools.rmdir()
    code, out, _ = run(capsys, "status", str(old_save(saves, "Later.ck3")), "--game-dir", str(g), "--allow-run",
                       "--reference", "none")
    assert code == 0
    # the path is longer than the line, so it breaks mid-path: compare with the spacing taken out
    nospace = lambda t: re.sub(r"\s", "", t)       # noqa: E731
    assert nospace(f"--var tools={tools.as_posix()}, which no longer exists; not used") in nospace(out)
    assert "needs --var tools (the folder holding copy.py)" in out


def test_no_record_neither_reads_nor_writes(tmp_path, saves, capsys):
    g = game(tmp_path)
    assert update(capsys, old_save(saves), g, "--no-record")[0] == 0
    assert not record.games_dir().exists()
    assert update(capsys, old_save(saves, "B.ck3"), g)[0] == 0          # now one is written
    code, out, _ = update(capsys, old_save(saves, "C.ck3"), g, "--no-record")
    assert code == 0 and "status: not used (--no-record)" in out
    assert len(record.read_record("111")["update"]) == 1


def test_status_and_a_dry_run_write_no_record(tmp_path, saves, capsys):
    g = game(tmp_path)
    s = old_save(saves)
    before = sorted(p.name for p in record.games_dir().parent.iterdir()) if record.games_dir().parent.exists() else []
    assert run(capsys, "status", str(s), "--game-dir", str(g), "--reference", "none")[0] == 0
    assert update(capsys, s, g, "--dry-run")[0] == 0
    after = sorted(p.name for p in record.games_dir().parent.iterdir()) if record.games_dir().parent.exists() else []
    assert after == before and not record.games_dir().exists()


def test_the_record_write_is_atomic(tmp_path, monkeypatch):
    record.append_update("42", "Camp", {"date": "d1", "tool": "t"})
    before = record.record_path("42").read_bytes()
    from dazzle_filekit import operations as ops

    def no_replace(*a, **k):
        raise OSError("simulated: the disk filled up")
    monkeypatch.setattr(ops.os, "replace", no_replace)
    with pytest.raises(OSError, match="simulated"):
        record.append_update("42", "Camp", {"date": "d2", "tool": "t"})
    assert record.record_path("42").read_bytes() == before
    assert [r["date"] for r in record.read_record("42")["update"]] == ["d1"]


# --------------------------------------------------------------------------- --in-place
def test_in_place_gives_the_same_bytes_as_dash_o_and_keeps_a_backup(tmp_path, saves, capsys):
    g = game(tmp_path)
    a, b = old_save(saves, "A.ck3"), old_save(saves, "B.ck3")
    original = b.read_bytes()
    out = tmp_path / "a_out.ck3"
    assert update(capsys, a, g, "-o", str(out), "--no-record")[0] == 0
    code, said, err = update(capsys, b, g, "--in-place", "--no-record")
    assert code == 0, err
    assert b.read_bytes() == out.read_bytes()
    assert (saves / "B.bak.ck3").read_bytes() == original
    rep = json.loads((saves / "B.report.json").read_text(encoding="utf-8"))
    assert Path(rep["output"]) == b.resolve()
    assert not list(saves.glob("*ck3update-tmp*"))


def test_in_place_refuses_an_existing_backup_without_force(tmp_path, saves, capsys):
    g = game(tmp_path)
    s = old_save(saves, "A.ck3")
    (saves / "A.bak.ck3").write_bytes(b"mine")
    original = s.read_bytes()
    assert update(capsys, s, g, "--in-place")[0] == 2
    assert s.read_bytes() == original and (saves / "A.bak.ck3").read_bytes() == b"mine"
    assert update(capsys, s, g, "--in-place", "--force")[0] == 0
    assert (saves / "A.bak.ck3").read_bytes() == original


def test_a_failed_second_rename_leaves_the_original_under_its_name(tmp_path, saves, capsys, monkeypatch):
    g = game(tmp_path)
    s = old_save(saves, "A.ck3")
    original = s.read_bytes()
    real = os.replace

    def flaky(src, dst):
        if str(src).endswith("ck3update-tmp.ck3") and Path(dst) == s:
            raise OSError("simulated: the file is locked")
        return real(src, dst)
    monkeypatch.setattr(cli.os, "replace", flaky)
    code, _, err = update(capsys, s, g, "--in-place")
    assert code == 1 and "the original is unchanged" in err and str(s) in err
    assert s.read_bytes() == original and not (saves / "A.bak.ck3").exists()


def test_in_place_with_dash_o_is_refused(tmp_path, saves, capsys):
    code, _, err = update(capsys, old_save(saves), game(tmp_path), "--in-place", "-o", str(tmp_path / "x.ck3"))
    assert code == 1 and "does not take -o" in err


def broken_lint(monkeypatch):
    """Lint finds an error in every output (test_update's exit-4 method)."""
    from ck3_save_migrator import lint as L

    def broken(g, **k):
        rep = L.LintReport()
        rep.add("braces balance", "error", ["simulated"])
        return rep
    monkeypatch.setattr(cli, "lint_gamestate", broken)


def test_in_place_with_a_lint_error_leaves_the_original_and_puts_the_output_at_the_default_name(
        tmp_path, saves, capsys, monkeypatch):
    broken_lint(monkeypatch)
    g = game(tmp_path)
    s = old_save(saves, "A.ck3")
    original = s.read_bytes()
    code, _, err = run(capsys, "update", str(s), "--game-dir", str(g), "--reference", "none", "--in-place")
    assert code == 4
    assert s.read_bytes() == original and not (saves / "A.bak.ck3").exists()
    out = saves / "A__updated__1.20.1.2.ck3"
    assert out.is_file() and out.with_suffix(".lint.json").is_file()
    rep = json.loads(out.with_suffix(".report.json").read_text(encoding="utf-8"))
    assert Path(rep["output"]) == out.resolve()
    assert f"lint found errors: the update was not put in place; it is at {out} for inspection" in err
    assert not list(saves.glob("*ck3update-tmp*")) and not (saves / "A.report.json").exists()
    assert not record.games_dir().exists()                         # exit 4 writes no record


def test_the_two_output_refusal_leaves_nothing_behind(tmp_path, saves, capsys, monkeypatch):
    s = old_save(saves, "A.ck3")
    original = s.read_bytes()

    def two_outputs(args, rules, user_packs, out, state=None, variables=None):
        args.written = []
        for shape in ("faith", "rite"):
            o = out.with_name(f"{out.stem}__wos-{shape}.ck3")
            o.write_bytes(b"x")
            o.with_suffix(".lint.json").write_text("{}", encoding="utf-8")
            args.written.append((o, "sha"))
        Path(args.report).write_text("{}", encoding="utf-8")
        return 0
    monkeypatch.setattr(cli, "execute_rules", two_outputs)
    code, _, err = update(capsys, s, game(tmp_path), "--in-place")
    assert code == 1 and "--in-place needs one output" in err
    assert sorted(p.name for p in saves.iterdir()) == ["A.ck3"] and s.read_bytes() == original
