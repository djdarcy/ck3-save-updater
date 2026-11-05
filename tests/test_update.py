"""The update driver (plan.py, and the status / update commands): one plan behind status, update --dry-run and update.

Every game here is a temporary game folder with a launcher-settings.json giving its version; the save folder is a
temporary folder (the plan's and the save-name lookup's save_games_dir are pointed at it). Saves carry a top-level
random_seed: the measured link between a save and what descends from it."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from ck3_save_migrator import cli, discover
from ck3_save_migrator import plan as PL
from ck3_save_migrator import savefile as sf
from ck3_save_migrator.patches import pack as P
from ck3_save_migrator.rules import RuleContext, run_rules, select
from ck3_save_migrator import userpacks as U
from tests.fixtures.make_ck3 import build_ck3, make_game_dir
from tests.fixtures.religion import OLD_BODY, OLD_META, REF_BODY, REF_META

SEED = b"random_seed=111\n"
BOOKMARK = b'\tmods={ "mod/zz_ref_987_10_27.mod" }\n'


def game(tmp_path, version: str | None = "1.20.1.2", name: str = "CK3") -> Path:
    g = make_game_dir(tmp_path / name / "game")
    if version:
        (g.parent / "launcher").mkdir(exist_ok=True)
        (g.parent / "launcher" / "launcher-settings.json").write_text(json.dumps({"rawVersion": version}))
    return g


def old_save(folder: Path, name: str = "Campaign.ck3", body_extra: bytes = b"") -> Path:
    s = folder / name
    s.write_bytes(build_ck3(meta=OLD_META, body=OLD_BODY + SEED + body_extra))
    return s


def ref_save(folder: Path, name: str, *, seed: bytes = b"random_seed=222\n", bookmark: bool = False,
             version: bytes = b"1.20.1.2", date: bytes = b"987.10.27") -> Path:
    meta = REF_META.replace(b'"1.20.1.2"', b'"' + version + b'"').replace(b"meta_date=987.10.27",
                                                                          b"meta_date=" + date)
    if bookmark:
        meta = meta.replace(b"\tironman=no\n", b"\tironman=no\n" + BOOKMARK)
    s = folder / name
    s.write_bytes(build_ck3(meta=meta, body=REF_BODY + seed))
    return s


@pytest.fixture(autouse=True)
def no_reference_from_the_environment(monkeypatch):
    """conftest sets CK3_REFERENCE_SAVE=none for every test; these test the search the variable would skip."""
    monkeypatch.delenv("CK3_REFERENCE_SAVE", raising=False)


@pytest.fixture
def saves(tmp_path, monkeypatch) -> Path:
    """The save folder: plan.py and the save-name lookup look here."""
    folder = tmp_path / "save games"
    folder.mkdir()
    monkeypatch.setattr(PL, "save_games_dir", lambda: folder)
    monkeypatch.setattr(discover, "save_games_dir", lambda **kw: folder)
    return folder


def run(capsys, *argv) -> tuple[int, str, str]:
    code = cli.main(list(argv))
    o, e = capsys.readouterr()
    return code, o, e


def flat(out: str) -> str:
    """The plan's blocks with each wrapped value joined back to one line (a continuation line is indented)."""
    return re.sub(r"\n {5,}", " ", out)


def untimed(out: str) -> str:
    """The output with what differs from run to run replaced by a mark: wall times, and the block-index cache's line
    (the first run writes the cache, the next reads it)."""
    out = re.sub(r"(?m)^( +cache: ).*(\n {10,}\S.*)*", r"\1...", out)
    return re.sub(r"slowest .*", "slowest ...", re.sub(r"\d+\.\d s\b", "#.# s", out))


def steps_of(out: str) -> dict:
    """The patches table by id: each row with a reason that went to the line below it joined back on."""
    rows: dict = {}
    last = None
    for ln in out.splitlines():
        if re.match(r"  \S+ +\S", ln):
            last = ln.split()[0]
            rows[last] = ln
        elif last is not None and ln.startswith("       ") and ln.strip():
            rows[last] += "  " + ln.strip()
        else:
            last = None
    return rows


# --------------------------------------------------------------------------- the plan reads no gamestate
def test_the_plan_parses_no_gamestate_and_reads_one_bounded_megabyte(tmp_path, saves, monkeypatch):
    big = old_save(saves, body_extra=b"pad={\n" + b"\tx=1\n" * 600_000 + b"}\n")       # a gamestate over 3 MB
    ref_save(saves, "Ref.ck3", bookmark=True)

    def no(*a, **k):
        pytest.fail("the plan parsed a whole save")
    monkeypatch.setattr(sf, "read_save", no)
    monkeypatch.setattr(sf, "parse_save", no)
    p = PL.plan_update(big, game_dir=str(game(tmp_path)))
    assert p.gamestate_bytes_read == PL.FIRST_MB and p.reference.how == "found in the save folder"


def test_a_text_save_is_read_from_its_text(tmp_path):
    s = tmp_path / "debug.ck3"
    s.write_bytes(b"SAV01007d3b003700000000\n" + OLD_META + b"x=1\n" + SEED)
    light = PL.read_light(s)
    assert light.meta == OLD_META and light.random_seed == "111"


# --------------------------------------------------------------------------- status and update share one plan
def test_status_and_update_print_and_run_the_same_plan(tmp_path, saves, capsys):
    s, g = old_save(saves), game(tmp_path)
    ref_save(saves, "Ref.ck3", bookmark=True)
    before = sorted(p.name for p in saves.iterdir())
    code, out, _ = run(capsys, "status", str(s), "--game-dir", str(g))
    assert code == 0 and re.search(r"(?m)^PATCHES +\(in the order they run\)$", out)
    code, dry, _ = run(capsys, "update", str(s), "--game-dir", str(g), "--dry-run", "--no-lint", "--wos-shape", "faith")
    assert code == 0 and "dry run: the plan with each patch's counts" in dry
    assert sorted(p.name for p in saves.iterdir()) == before                       # status and --dry-run wrote nothing
    assert [(x.id, x.will_run) for x in cli.LAST_PLAN["update"].steps] == \
        [(x.id, x.will_run) for x in cli.LAST_PLAN["status"].steps]
    assert run(capsys, "update", str(s), "--game-dir", str(g), "--no-lint", "--wos-shape", "faith")[0] == 0
    assert cli.LAST_PLAN["update"].as_dict() == cli.LAST_PLAN["status"].as_dict()   # the plan status printed ...
    assert cli.LAST_PLAN["ran"] == cli.LAST_PLAN["status"].running()               # ... is the plan update ran
    out_path = saves / "Campaign__updated__1.20.1.2.ck3"
    assert out_path.is_file() and (saves / "Campaign__updated__1.20.1.2.report.json").is_file()
    rep = json.loads((saves / "Campaign__updated__1.20.1.2.report.json").read_text(encoding="utf-8"))
    assert [s["id"] for s in rep["plan"]["steps"] if s["will_run"]] == [r["id"] for r in rep["rules"]]


def test_colour_is_off_under_no_color_and_the_forced_colour_is_the_same_text(tmp_path, saves, capsys, monkeypatch):
    """The plain form is pinned under NO_COLOR (which beats FORCE_COLOR); forced colour adds escapes and nothing
    else. The verdict comes first (the wtf tools' shape). colorama is kept from wrapping pytest's streams."""
    import re
    from ck3_save_migrator._vendor import colors
    monkeypatch.setattr(colors, "_ansi_initialized", True)
    s, g = old_save(saves), game(tmp_path)
    monkeypatch.setenv("FORCE_COLOR", "1")
    monkeypatch.setenv("NO_COLOR", "1")
    code, plain, plain_err = run(capsys, "status", str(s), "--game-dir", str(g))
    assert code == 0 and "\033[" not in plain + plain_err and plain.startswith("READY  1.8.1 -> 1.20.1.2:")
    monkeypatch.delenv("NO_COLOR")
    code, coloured, _ = run(capsys, "status", str(s), "--game-dir", str(g))
    assert code == 0 and "\033[" in coloured
    assert untimed(re.sub(r"\033\[[0-9;]*m", "", coloured)) == untimed(plain)


def test_status_and_a_dry_run_never_create_the_packs_folder_and_update_does(tmp_path, saves, capsys):
    """CK3SM_CONFIG is in a temporary folder (conftest) with no packs folder beside it yet."""
    s, g = old_save(saves), game(tmp_path)
    assert not U.packs_dir().exists()
    assert run(capsys, "status", str(s), "--game-dir", str(g))[0] == 0
    assert not U.packs_dir().exists()
    assert run(capsys, "update", str(s), "--game-dir", str(g), "--dry-run", "--no-lint")[0] == 0
    assert not U.packs_dir().exists() and not U.packs_dir().parent.exists()
    assert run(capsys, "update", str(s), "--game-dir", str(g), "--no-lint")[0] == 0
    assert (U.packs_dir() / "README.md").is_file()                  # update itself may, as migrate does


# --------------------------------------------------------------------------- version spans and the gap
def test_a_1_8_save_with_a_1_20_game_selects_the_built_in_pack(tmp_path, saves):
    p = PL.plan_update(old_save(saves), game_dir=str(game(tmp_path)))
    assert p.packs[0].id == "to_1_20" and p.packs[0].selected and not p.refusals and p.has_changes()
    assert "save 1.8.1 matches >=1.8, <1.20; game 1.20.1.2 matches >=1.20, <1.21" in p.packs[0].why


def test_a_save_at_the_games_version_is_already_current(tmp_path, saves, capsys):
    s = ref_save(saves, "Current.ck3")
    code, out, _ = run(capsys, "update", str(s), "--game-dir", str(game(tmp_path)))
    assert code == 0 and "already current: nothing written" in out
    assert sorted(p.name for p in saves.iterdir()) == ["Current.ck3"]


def test_a_gap_no_pack_covers_is_named_and_nothing_is_written(tmp_path, saves, capsys):
    s = ref_save(saves, "Current.ck3")
    g = game(tmp_path, "1.21.0")
    code, out, err = run(capsys, "update", str(s), "--game-dir", str(g))
    assert code == 1 and "NOT COVERED: the gap 1.20.1.2 -> 1.21.0" in out and "the gap 1.20.1.2 -> 1.21.0" in err
    assert sorted(p.name for p in saves.iterdir()) == ["Current.ck3"]
    # a pack of yours that declares it covers 1.20 -> 1.21 is selected, and the update runs
    folder = U.packs_dir() / "to_1_21"
    (folder / "N1-flag").mkdir(parents=True)
    (folder / "pack.toml").write_text('format = 1\nid = "to_1_21"\ntitle = "t"\norder = ["N1"]\n\n[applies]\n'
                                      'save = ">=1.20, <1.21"\ngame = ">=1.21, <1.22"\n', encoding="utf-8")
    (folder / "N1-flag" / "patch.toml").write_text(
        'format = 1\nid = "N1"\nname = "flag"\ntitle = "t"\nsince = "1.21"\ndone = { path = "meta_data", key = "n1" }'
        '\n\n[[edit]]\npath = "meta_data"\nop = "insert"\nposition = "end"\npayload = "\\tn1=yes\\n"\n', encoding="utf-8")
    code, out, err = run(capsys, "update", str(s), "--game-dir", str(g), "--no-lint")
    assert code == 0, err
    assert cli.LAST_PLAN["ran"] == ["N1"] and (saves / "Current__updated__1.21.0.ck3").is_file()


def test_a_save_newer_than_the_game_is_refused(tmp_path, saves, capsys):
    code, out, err = run(capsys, "status", str(old_save(saves)), "--game-dir", str(game(tmp_path, "1.8.0")))
    assert code == 1 and "newer than the game" in err and "REFUSED" in out


def test_an_old_game_dir_that_is_not_a_game_folder_is_refused_before_anything_runs(tmp_path, saves, capsys):
    """The 0.4.0 sweep (2026-11-02): a shell ate the backslashes of --old-game-dir, R15 read a map with no titles,
    and the output linted with two orphaned baronies. A given folder is checked first; a wrong one refuses."""
    g, s = game(tmp_path), old_save(saves)
    gone = tmp_path / "no-such-folder"
    code, out, err = run(capsys, "update", str(s), "--game-dir", str(g), "--old-game-dir", str(gone), "--no-lint")
    assert code == 1 and "REFUSED" in out and "is not a folder" in err and "fix: give the 'game' folder" in err
    assert not list(saves.glob("*__updated__*"))                                   # nothing written
    empty = tmp_path / "not-a-game"
    empty.mkdir()
    code, _, err = run(capsys, "status", str(s), "--game-dir", str(g), "--old-game-dir", str(empty))
    assert code == 1 and "has no common/landed_titles" in err
    (empty / "common" / "landed_titles").mkdir(parents=True)                       # now shaped like a game folder
    code, _, err = run(capsys, "status", str(s), "--game-dir", str(g), "--old-game-dir", str(empty))
    assert "old-game-dir" not in err


def test_a_pack_without_a_span_says_so(tmp_path, saves):
    folder = U.packs_dir() / "mine"
    (folder / "M1-x").mkdir(parents=True)
    (folder / "pack.toml").write_text('format = 1\nid = "mine"\ntitle = "t"\norder = ["M1"]\n', encoding="utf-8")
    (folder / "M1-x" / "patch.toml").write_text('format = 1\nid = "M1"\nname = "x"\ntitle = "t"\nsince = "1"\n\n'
                                                '[[edit]]\npath = "meta_data"\nop = "delete_key"\nkey = "nothing"\n',
                                                encoding="utf-8")
    p = PL.plan_update(old_save(saves), game_dir=str(game(tmp_path)))
    assert [(x.id, x.selected, x.why) for x in p.packs[1:]] == [
        ("mine", True, "no version span declared (matches any version)")]


# --------------------------------------------------------------------------- the reference save
def test_a_reference_given_wins(tmp_path, saves):
    r = ref_save(tmp_path, "Mine.ck3")
    ref_save(saves, "Other.ck3", bookmark=True)
    p = PL.plan_update(old_save(saves), game_dir=str(game(tmp_path)), reference=str(r))
    assert (p.reference.path, p.reference.how) == (str(r), "given")


def test_one_save_of_the_games_version_and_the_saves_date_is_found(tmp_path, saves):
    r = ref_save(saves, "Fresh.ck3")
    ref_save(saves, "OtherDate.ck3", seed=b"random_seed=333\n", date=b"990.1.1")
    ref_save(saves, "OtherVersion.ck3", seed=b"random_seed=444\n", version=b"1.20.0")
    p = PL.plan_update(old_save(saves), game_dir=str(game(tmp_path)))
    assert p.reference.path == str(r) and "the one save written by 1.20.1.2 on 987.10.27" in p.reference.why


def test_with_no_reference_the_skipping_rules_and_the_steps_are_printed(tmp_path, saves, capsys):
    code, out, _ = run(capsys, "status", str(old_save(saves)), "--game-dir", str(game(tmp_path)))
    assert code == 0 and "without one these skip: R8, R10, R9, R12" in out
    assert "ck3update reference-mod --save" in out and "docs/reference-save.md" in out


# --------------------------------------------------------------------------- the decoy (the director's test)
def test_the_true_reference_is_chosen_beside_a_decoy_that_descends_from_the_save(tmp_path, saves):
    s = old_save(saves)
    true = ref_save(saves, "Fresh987.ck3", bookmark=True)
    ref_save(saves, "Played_resaved.ck3", seed=SEED)          # our output, saved again by the game: the save's seed
    p = PL.plan_update(s, game_dir=str(game(tmp_path)))
    assert p.reference.path == str(true) and "1 left out" in p.reference.why


def test_with_the_true_reference_gone_the_decoy_is_never_chosen(tmp_path, saves):
    s = old_save(saves)
    ref_save(saves, "Played_resaved.ck3", seed=SEED)
    p = PL.plan_update(s, game_dir=str(game(tmp_path)))
    assert p.reference.path is None and "descends from this save" in p.reference.why


def test_two_fresh_references_without_a_bookmark_mod_are_refused_naming_both(tmp_path, saves, capsys):
    s = old_save(saves)
    a = ref_save(saves, "A.ck3")
    b = ref_save(saves, "B.ck3", seed=b"random_seed=333\n")
    code, out, err = run(capsys, "status", str(s), "--game-dir", str(game(tmp_path)))
    # each refusal once, on stderr: the folder once, then the names, then the fix (the 01:42 layout ruling)
    assert code == 1 and a.name in err and b.name in err and str(a.parent) in err and "pick one with --reference" in err
    assert err.count(str(a.parent)) == 1 and "REFUSED" in out and str(a) not in out
    assert (out + err).count("pick one with --reference") == 1 and (out + err).count(b.name) == 1


def test_of_two_fresh_saves_the_one_with_the_bookmark_mod_is_chosen(tmp_path, saves):
    s = old_save(saves)
    ref_save(saves, "Plain.ck3")
    bm = ref_save(saves, "WithBookmark.ck3", seed=b"random_seed=333\n", bookmark=True)
    p = PL.plan_update(s, game_dir=str(game(tmp_path)))
    assert p.reference.path == str(bm) and "with a zz_ref bookmark mod" in p.reference.why


def test_a_save_with_a_report_beside_it_is_never_chosen(tmp_path, saves):
    s = old_save(saves)
    ours = ref_save(saves, "Ours.ck3", seed=b"random_seed=999\n", bookmark=True)
    ours.with_suffix(".report.json").write_text("{}", encoding="utf-8")
    p = PL.plan_update(s, game_dir=str(game(tmp_path)))
    assert p.reference.path is None


# --------------------------------------------------------------------------- exit codes, output
def test_exit_0_writes_the_default_output_beside_the_save(tmp_path, saves, capsys):
    s = old_save(saves)
    assert run(capsys, "update", s.stem, "--game-dir", str(game(tmp_path)), "--no-lint")[0] == 0   # by name
    assert (saves / "Campaign__updated__1.20.1.2.ck3").is_file()


def test_exit_2_for_an_existing_output_and_force(tmp_path, saves, capsys):
    s, g = old_save(saves), game(tmp_path)
    out = saves / "Campaign__updated__1.20.1.2.ck3"
    out.write_bytes(b"mine")
    code, txt, err = run(capsys, "update", str(s), "--game-dir", str(g), "--no-lint")
    assert code == 2 and "exists" in txt and out.read_bytes() == b"mine"
    assert run(capsys, "update", str(s), "--game-dir", str(g), "--no-lint", "--force")[0] == 0
    assert out.read_bytes() != b"mine"
    assert run(capsys, "update", str(s), "--game-dir", str(g), "-o", str(s), "--no-lint")[0] == 2    # in place


def test_exit_3_when_the_written_file_fails_verification(tmp_path, saves, capsys, monkeypatch):
    def bad(*a, **k):
        raise sf.VerifyError("simulated")
    monkeypatch.setattr(sf, "verify_bytes", bad)
    assert run(capsys, "update", str(old_save(saves)), "--game-dir", str(game(tmp_path)), "--no-lint")[0] == 3


def test_exit_4_when_lint_finds_an_error_and_the_output_is_still_written(tmp_path, saves, capsys, monkeypatch):
    from ck3_save_migrator import lint as L

    def broken(g, **k):
        rep = L.LintReport()
        rep.add("braces balance", "error", ["simulated"])
        return rep
    monkeypatch.setattr(cli, "lint_gamestate", broken)
    assert run(capsys, "update", str(old_save(saves)), "--game-dir", str(game(tmp_path)))[0] == 4
    assert (saves / "Campaign__updated__1.20.1.2.ck3").is_file()


def test_exit_5_when_a_patch_fails_and_nothing_is_written(tmp_path, saves, capsys):
    folder = U.packs_dir() / "strict"
    (folder / "S1-must").mkdir(parents=True)
    (folder / "pack.toml").write_text('format = 1\nid = "strict"\ntitle = "t"\norder = ["S1"]\n', encoding="utf-8")
    (folder / "S1-must" / "patch.toml").write_text(
        'format = 1\nid = "S1"\nname = "must"\ntitle = "t"\nsince = "1"\n\n[[edit]]\npath = "meta_data"\n'
        'op = "delete_key"\nkey = "not_there"\nexpect = { min = 1 }\n', encoding="utf-8")
    code, _, err = run(capsys, "update", str(old_save(saves)), "--game-dir", str(game(tmp_path)), "--no-lint")
    assert code == 5 and "patch S1 (must) failed" in err
    assert not (saves / "Campaign__updated__1.20.1.2.ck3").exists()


def test_no_game_or_an_unreadable_game_version_is_refused(tmp_path, saves, capsys):
    assert run(capsys, "update", str(old_save(saves)))[0] == 1                       # CK3_GAME_DIR=none
    code, _, err = run(capsys, "update", str(old_save(saves, "B.ck3")), "--game-dir", str(game(tmp_path, None)))
    assert code == 1 and "version could not be read" in err


# --------------------------------------------------------------------------- after =
def after_pack(after: str | None) -> None:
    folder = U.packs_dir() / "later"
    (folder / "A1-flag").mkdir(parents=True, exist_ok=True)
    (folder / "pack.toml").write_text('format = 1\nid = "later"\ntitle = "t"\norder = ["A1"]\n'
                                      + (f'after = "{after}"\n' if after else ""), encoding="utf-8")
    (folder / "A1-flag" / "patch.toml").write_text(
        'format = 1\nid = "A1"\nname = "flag"\ntitle = "t"\nsince = "1"\ndone = { path = "meta_data", key = "a1" }'
        '\n\n[[edit]]\npath = "meta_data"\nop = "insert"\nposition = "end"\npayload = "\\ta1=yes\\n"\n', encoding="utf-8")


def test_a_pack_after_r17_runs_between_r17_and_r7(tmp_path, saves, capsys):
    after_pack("R17")
    g, r = game(tmp_path), ref_save(tmp_path, "Ref.ck3")
    code, _, err = run(capsys, "update", str(old_save(saves)), "--game-dir", str(g), "--reference", str(r),
                       "--rules", "all,R14,R16", "--no-lint", "--wos-shape", "faith")
    assert code == 0, err
    ran = cli.LAST_PLAN["ran"]
    # R19 finishes what R17 wrote: the pack follows; R25 and R26 (key renames, no writer) and the bump come after
    assert ran[-9:] == ["R17", "R19", "A1", "R25", "R26", "R27", "R28", "R29", "R7"]
    assert run(capsys, "update", str(old_save(saves, "C2.ck3")), "--game-dir", str(g), "--no-lint")[0] == 0
    assert cli.LAST_PLAN["ran"][-7:] == ["A1", "R25", "R26", "R27", "R28", "R29", "R7"]         # R17 skipped: still before R7


def test_without_after_a_pack_runs_after_the_built_in_rules(tmp_path, saves, capsys):
    after_pack(None)
    assert run(capsys, "update", str(old_save(saves)), "--game-dir", str(game(tmp_path)), "--no-lint")[0] == 0
    assert cli.LAST_PLAN["ran"][-2:] == ["R7", "A1"]


def test_an_unknown_after_id_is_refused(tmp_path, saves, capsys):
    after_pack("R99")
    code, _, err = run(capsys, "status", str(old_save(saves)), "--game-dir", str(game(tmp_path)))
    assert code == 1 and "after = 'R99'" in err


# --------------------------------------------------------------------------- trust, as #28
def test_an_untrusted_code_pack_is_listed_and_never_runs(tmp_path, saves, capsys, monkeypatch):
    def boom(*a, **k):
        pytest.fail("a pack's code was reached")
    monkeypatch.setattr(P, "_function", boom)
    monkeypatch.setattr(P, "run_patch", boom)
    folder = U.packs_dir() / "code"
    (folder / "C1-x").mkdir(parents=True)
    (folder / "pack.toml").write_text('format = 1\nid = "code"\ntitle = "t"\norder = ["C1"]\n', encoding="utf-8")
    (folder / "C1-x" / "patch.toml").write_text('format = 1\nid = "C1"\nname = "x"\ntitle = "t"\nsince = "1"\n'
                                                'script = "f.py:apply"\n', encoding="utf-8")
    (folder / "C1-x" / "f.py").write_text("def apply(save, ctx, rule):\n    raise SystemExit(9)\n", encoding="utf-8")
    code, out, _ = run(capsys, "update", str(old_save(saves)), "--game-dir", str(game(tmp_path)), "--no-lint")
    assert code == 0 and re.search(r"(?m)^ +code: \S.*\(yours, not trusted\)", out)
    assert "C1" not in cli.LAST_PLAN["ran"]
    assert "its pack is not trusted: `ck3update trust code` lets it run" in steps_of(out)["C1"]


# --------------------------------------------------------------------------- the plan's rule table agrees with the rules
def test_the_rules_the_plan_says_need_a_reference_do_nothing_without_one(tmp_path):
    from tests.fixtures.make_ck3 import RULES_BODY, RULES_META
    save = sf.parse_save(build_ck3(meta=RULES_META, body=RULES_BODY))
    res = {r.id: r for r in run_rules(save, select("all,R14,R15,R16"), RuleContext(reference=None))}
    for rid in PL.NEEDS_REFERENCE + PL.NEEDS_OLD_GAME:
        assert res[rid].edited == 0 and res[rid].extra.get("skipped"), rid


# --------------------------------------------------------------------------- the span syntax
def test_spans_are_comma_separated_comparisons_on_dotted_versions():
    from ck3_save_migrator.patches.model import parse_span, span_matches
    assert parse_span(">=1.8, <1.20") == [(">=", "1.8"), ("<", "1.20")] and parse_span("1.20") == [("==", "1.20")]
    assert span_matches(">=1.8, <1.20", "1.8.1") and not span_matches(">=1.8, <1.20", "1.20.1.2")
    assert span_matches(">=1.20, <1.21", "1.20.1.2") and span_matches("!=1.9", "1.10")
    assert span_matches(">=1.8", None) is None
    with pytest.raises(ValueError, match="not a comparison"):
        parse_span(">= one")


def test_a_bad_applies_table_is_refused_when_the_pack_loads(tmp_path):
    from ck3_save_migrator.patches import read_pack
    from ck3_save_migrator.patches.model import PatchError
    (tmp_path / "p" / "Q1-x").mkdir(parents=True)
    (tmp_path / "p" / "pack.toml").write_text('format = 1\nid = "p"\ntitle = "t"\norder = ["Q1"]\n\n[applies]\n'
                                              'save = "about 1.8"\n', encoding="utf-8")
    (tmp_path / "p" / "Q1-x" / "patch.toml").write_text('format = 1\nid = "Q1"\nname = "x"\ntitle = "t"\n'
                                                        'since = "1"\n\n[[edit]]\npath = "a"\nop = "delete_key"\n'
                                                        'key = "b"\n', encoding="utf-8")
    with pytest.raises(PatchError, match=r"\[applies\] save"):
        read_pack(tmp_path / "p")
