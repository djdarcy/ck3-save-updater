"""U1, requirements: every decision about what runs, what is skipped and why is made in the plan, before anything runs.

Campaign scope (a pack for one save game), the hotfix rule (a gap within one major.minor line), the reference only
when a step that will run needs one, a run patch's needs and done checks, patch-qualified variables, `help`, and
the new-map transplant chosen by need behind a switch. Games and save folders are temporary folders
(tests/test_update.py's helpers); every program a test runs is one it wrote into tmp_path, and wherever a test
asserts that something does not run, the code that would run it is patched to fail the test.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from ck3_save_migrator import cli, config
from ck3_save_migrator import plan as PL
from ck3_save_migrator import savefile as sf
from ck3_save_migrator import userpacks as U
from ck3_save_migrator.patches import pack as P
from ck3_save_migrator.patches import run as RUN
from tests.fixtures.make_ck3 import build_ck3
from tests.fixtures.religion import OLD_BODY, OLD_META
from tests import test_update as TU
from tests.test_update import game, old_save, ref_save, run

# test_update's fixtures, used here by name: the save folder, and no reference from the environment
saves = TU.saves
no_reference_from_the_environment = TU.no_reference_from_the_environment

PY = sys.executable.replace("\\", "/")


def other_world(folder: Path, name: str = "Other.ck3") -> Path:
    s = folder / name
    s.write_bytes(build_ck3(meta=OLD_META, body=OLD_BODY + b"random_seed=999\n"))
    return s


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def flag_pack(pack_id: str, patch_id: str, applies: str = "") -> Path:
    folder = U.packs_dir() / pack_id
    write(folder / "pack.toml", f'format = 1\nid = "{pack_id}"\ntitle = "t"\norder = ["{patch_id}"]\n' + applies)
    write(folder / f"{patch_id}-flag" / "patch.toml",
          f'format = 1\nid = "{patch_id}"\nname = "{patch_id.lower()}-flag"\ntitle = "add a flag"\nsince = "1"\n'
          f'done = {{ path = "meta_data", key = "{patch_id}_flag" }}\n\n[[edit]]\npath = "meta_data"\nop = "insert"\n'
          f'position = "end"\npayload = "\\t{patch_id}_flag=yes\\n"\n')
    return folder


def run_pack(pack_id: str, patches: dict[str, str]) -> Path:
    """A pack of run patches: {patch id: the text after [run]}."""
    folder = U.packs_dir() / pack_id
    write(folder / "pack.toml", f'format = 1\nid = "{pack_id}"\ntitle = "t"\norder = {json.dumps(list(patches))}\n')
    for pid, body in patches.items():
        write(folder / f"{pid}-run" / "patch.toml",
              f'format = 1\nid = "{pid}"\nname = "{pid.lower()}-run"\ntitle = "a program"\nsince = "1"\n' + body)
    return folder


COPY_AND_WRITE = """import shutil, sys
from pathlib import Path
shutil.copyfile(sys.argv[1], sys.argv[2])
Path(sys.argv[4]).write_text(sys.argv[3], encoding="utf-8")
"""


@pytest.fixture
def never_runs(monkeypatch):
    """The run-patch executor and the done_command runner fail the test if reached."""
    def boom(*a, **k):
        pytest.fail("a program was run")
    monkeypatch.setattr(P, "run_patch", boom)
    monkeypatch.setattr(RUN, "run_done_command", boom)


# --------------------------------------------------------------------------- 1. campaign scope
def test_a_campaign_pack_runs_on_its_own_save_game_and_is_skipped_on_another(tmp_path, saves, capsys):
    flag_pack("beidh", "B1", '\n[applies]\ncampaign = { name = "Beidh", seed = 111 }\n')
    g = str(game(tmp_path))
    mine = PL.plan_update(old_save(saves), game_dir=g)
    assert next(s for s in mine.steps if s.id == "B1").will_run
    theirs = PL.plan_update(other_world(saves), game_dir=g)
    step = next(s for s in theirs.steps if s.id == "B1")
    assert not step.will_run and step.reason == "for another save game (Beidh)"
    assert "campaign Beidh" in next(p.why for p in theirs.packs if p.id == "beidh")
    assert cli.main(["packs"]) == 0 and "(for the save game Beidh)" in capsys.readouterr().out


# --------------------------------------------------------------------------- 2. the hotfix rule
def test_a_hotfix_of_the_same_line_is_already_current(tmp_path, saves, capsys):
    s = ref_save(saves, "Current.ck3")                                   # 1.20.1.2
    code, out, _ = run(capsys, "update", str(s), "--game-dir", str(game(tmp_path, "1.20.1.3")))
    assert code == 0 and "ALREADY CURRENT" in out
    assert "no pack declares 1.20.1.2 -> 1.20.1.3 (same 1.20 line; assumed compatible)" in out
    assert sorted(p.name for p in saves.iterdir()) == ["Current.ck3"]


def test_another_line_with_no_pack_is_still_not_covered(tmp_path, saves, capsys):
    code, out, _ = run(capsys, "status", str(ref_save(saves, "C.ck3")), "--game-dir", str(game(tmp_path, "1.21.0")))
    assert code == 1 and "NOT COVERED" in out


# --------------------------------------------------------------------------- 3. the reference only when needed
def test_an_up_to_date_save_beside_two_candidates_is_not_refused(tmp_path, saves, capsys):
    ref_save(saves, "A.ck3")
    ref_save(saves, "B.ck3", seed=b"random_seed=333\n")
    current = ref_save(saves, "Mine.ck3", seed=b"random_seed=111\n")
    code, out, err = run(capsys, "status", str(current), "--game-dir", str(game(tmp_path)))
    assert code == 0 and "REFUSED" not in out + err and "ALREADY CURRENT" in out
    assert "not needed (no patch that will run needs one)" in out
    code, _, err = run(capsys, "status", str(old_save(saves)), "--game-dir", str(game(tmp_path)))
    assert code == 1 and "could each be the reference" in err                   # R8 runs: it needs one


# --------------------------------------------------------------------------- 4. needs, known before anything runs
def test_an_unmet_need_is_a_skipped_step_and_nothing_runs(tmp_path, saves, capsys, never_runs):
    run_pack("tools", {"T1": '\n[run]\ncommand = ["@@python@@", "@@tools_dir@@/fix.py", "@@input@@", "@@output@@"]\n'
                             'needs = { tools_dir = "the folder holding fix.py" }\n'})
    s = ref_save(saves, "Current.ck3")
    code, out, _ = run(capsys, "update", str(s), "--game-dir", str(game(tmp_path)), "--allow-run")
    assert code == 0
    assert "needs --var tools_dir (the folder holding fix.py)" in out
    assert "ALREADY CURRENT" in out and "T1 skipped for an unmet need" in out
    assert not any(line.startswith("READY") for line in out.splitlines())
    assert sorted(p.name for p in saves.iterdir()) == ["Current.ck3"]            # nothing written


# --------------------------------------------------------------------------- 5. done checks on run patches
def test_a_done_marker_decides_done_or_needed(tmp_path, saves, never_runs):
    run_pack("mark", {"D1": 'done = { path = "meta_data", key = "D1_ran" }\n\n[run]\n'
                            'command = ["@@python@@", "x.py", "@@input@@", "@@output@@"]\n'})
    g = str(game(tmp_path))
    plain = PL.plan_update(ref_save(saves, "A.ck3"), game_dir=g, allow_run=True)
    d1 = next(s for s in plain.steps if s.id == "D1")
    assert d1.will_run and d1.reason.startswith("needed: its done marker is absent")
    s = saves / "B.ck3"
    s.write_bytes(build_ck3(meta=b'meta_data={\n\tversion="1.20.1.2"\n\tmeta_date=987.10.27\n\tD1_ran=yes\n}\n',
                            body=b"random_seed=5\n"))
    done = next(x for x in PL.plan_update(s, game_dir=g, allow_run=True).steps if x.id == "D1")
    assert not done.will_run and done.reason.startswith("done: its done marker is present")


def done_pack(tmp_path) -> Path:
    script = write(tmp_path / "progs" / "is_done.py",
                   "import sys\nfrom pathlib import Path\np = Path(sys.argv[1])\n"
                   "Path(sys.argv[2]).write_text(str(p), encoding='utf-8')\n"
                   "p.write_bytes(b'tampered')\nsys.exit(0)\n")
    seen = tmp_path / "seen.txt"
    return run_pack("probe", {"Q1": f'\n[run]\ncommand = ["@@python@@", "x.py", "@@input@@", "@@output@@"]\n'
                                    f'done_command = ["@@python@@", "{script.as_posix()}", "@@input@@", '
                                    f'"{seen.as_posix()}"]\n'}), seen


def test_an_untrusted_done_command_is_unknown_and_never_started(tmp_path, saves, never_runs):
    done_pack(tmp_path)
    q1 = next(s for s in PL.plan_update(ref_save(saves, "A.ck3"), game_dir=str(game(tmp_path)),
                                        allow_run=False).steps if s.id == "Q1")
    assert not q1.will_run and "not trusted" in q1.reason                    # the pack itself is not trusted


def test_check_reports_an_untrusted_done_command_as_unknown(tmp_path, saves, capsys, never_runs):
    done_pack(tmp_path)
    assert cli.main(["check", str(ref_save(saves, "A.ck3"))]) == 0
    row = next(ln for ln in capsys.readouterr().out.splitlines() if ln.strip().startswith("Q1"))
    assert "unknown" in row and "done_command not run: not trusted" in row


def test_a_trusted_done_command_runs_on_a_copy_of_the_save(tmp_path, saves):
    _, seen = done_pack(tmp_path)
    s = ref_save(saves, "A.ck3")
    before = s.read_bytes()
    q1 = next(x for x in PL.plan_update(s, game_dir=str(game(tmp_path)), allow_run=True).steps if x.id == "Q1")
    assert not q1.will_run and q1.reason.startswith("done: done_command says it is done (exit 0); runs `")
    assert s.read_bytes() == before                                      # the program changed its copy only
    assert Path(seen.read_text(encoding="utf-8")).resolve() != s.resolve()


# --------------------------------------------------------------------------- 6. qualified variables
TWO = {pid: f'\n[run]\ncommand = ["@@python@@", "@@prog@@", "@@input@@", "@@output@@", "@@witness@@", '
            f'"@@out_{pid.lower()}@@"]\nneeds = ["witness", "prog", "out_{pid.lower()}"]\n'
       for pid in ("G1", "G2")}


def test_a_bare_variable_two_patches_of_one_pack_need_reaches_both(tmp_path, saves, capsys):
    """U3, correcting U1: within one pack a bare name is meant for all its patches (the play6 recipe's G1 and G2
    both need tools_dir, the same folder)."""
    run_pack("two", TWO)
    prog = write(tmp_path / "progs" / "copy.py", COPY_AND_WRITE)
    a, b = tmp_path / "a.txt", tmp_path / "b.txt"
    code, out, err = run(capsys, "update", str(ref_save(saves, "A.ck3")), "--game-dir", str(game(tmp_path)),
                         "--allow-run", "--no-lint", "--var", "witness=both", "--var", f"prog={prog.as_posix()}",
                         "--var", f"out_g1={a.as_posix()}", "--var", f"out_g2={b.as_posix()}")
    assert code == 0, err
    assert "REFUSED" not in err
    assert a.read_text(encoding="utf-8") == "both" and b.read_text(encoding="utf-8") == "both"


def test_a_bare_variable_patches_of_two_packs_need_is_refused_naming_both(tmp_path, saves, capsys):
    run_pack("one", {"G1": TWO["G1"]})
    run_pack("other", {"G2": TWO["G2"]})
    code, out, err = run(capsys, "status", str(ref_save(saves, "A.ck3")), "--game-dir", str(game(tmp_path)),
                         "--allow-run", "--var", "witness=x", "--var", "prog=p", "--var", "out_g1=a",
                         "--var", "out_g2=b")
    assert code == 1
    assert "--var witness is needed by patches of different packs, G1 (pack one), G2 (pack other)" in err
    assert "--var G1.witness=... --var G2.witness=..." in err


def test_a_qualified_variable_reaches_only_its_patch(tmp_path, saves, capsys):
    folder = run_pack("two", TWO)
    prog = write(tmp_path / "progs" / "copy.py", COPY_AND_WRITE)
    write(folder / "vars.toml", f'prog = "{prog.as_posix()}"\n')     # shared by both: the pack's vars.toml
    a, b = tmp_path / "a.txt", tmp_path / "b.txt"
    code, out, err = run(capsys, "update", str(ref_save(saves, "A.ck3")), "--game-dir", str(game(tmp_path)),
                         "--allow-run", "--no-lint", "--var", "G1.witness=one",
                         "--var", "G2.witness=two", "--var", f"G1.out_g1={a.as_posix()}",
                         "--var", f"out_g2={b.as_posix()}")
    assert code == 0, err
    assert a.read_text(encoding="utf-8") == "one" and b.read_text(encoding="utf-8") == "two"
    assert RUN.patch_vars("G1", {"G1.w": "x", "G2.w": "y", "z": "1"}) == {"z": "1", "w": "x"}


def test_a_qualified_variable_for_no_patch_is_refused(tmp_path, saves, capsys):
    code, _, err = run(capsys, "status", str(ref_save(saves, "A.ck3")), "--game-dir", str(game(tmp_path)),
                       "--var", "Z9.x=1")
    assert code == 1 and "--var Z9.x: no patch Z9" in err


# --------------------------------------------------------------------------- 7. help
def test_help_for_a_rule_a_pack_and_an_unknown_id(capsys):
    flag_pack("mine", "M1", '\n[applies]\ncampaign = { name = "Beidh", seed = 111 }\n')
    assert cli.main(["help", "R23"]) == 0
    out = capsys.readouterr().out
    for field in ("R23 nickname-text:", "pack      : to_1_20", "since     :", "default   : on", "done when :"):
        assert field in out, field
    assert cli.main(["help", "mine"]) == 0
    out = capsys.readouterr().out
    assert "campaign  : Beidh" in out and "patches   : M1" in out and "state     : runs" in out
    assert cli.main(["help", "R233"]) == 1
    err = capsys.readouterr().err
    assert "did you mean: " in err and len(err.split("did you mean: ")[1].split(",")) <= 3


# --------------------------------------------------------------------------- 8. the transplant, by need, behind a switch
def transplant_plan(tmp_path, saves, **kw):
    return PL.plan_update(old_save(saves), game_dir=str(game(tmp_path)), **kw)


def test_with_the_switch_off_the_transplant_is_skipped_and_the_line_shown(tmp_path, saves):
    p = transplant_plan(tmp_path, saves, reference=str(ref_save(tmp_path, "Ref.ck3")), transplant="off")
    assert not set(PL.TRANSPLANT) & set(p.running())
    assert any("crosses the 1.13-1.20 map rework" in n and "--transplant auto" in n for n in p.notes)


def test_auto_is_the_default_with_nothing_in_the_config(tmp_path, saves):
    """djdarcy, 2026-11-02: the transplant default "handles itself": a save from before the map rework with a
    reference gets the new-map steps without --transplant."""
    assert config.transplant_mode() == "auto"
    p = transplant_plan(tmp_path, saves, reference=str(ref_save(tmp_path, "Ref.ck3")))
    assert {"R14", "R16", "R17"} <= set(p.running())


def test_with_the_switch_on_and_a_reference_the_transplant_is_selected(tmp_path, saves):
    p = transplant_plan(tmp_path, saves, reference=str(ref_save(tmp_path, "Ref.ck3")), transplant="auto",
                        old_game_dir=str(tmp_path / "old"))
    assert {"R14", "R15", "R16", "R17"} <= set(p.running())
    p = transplant_plan(tmp_path, saves, reference=str(ref_save(tmp_path, "Ref2.ck3")), transplant="auto",
                        rules_spec="all,-R15")
    assert {"R14", "R16", "R17"} <= set(p.running()) and "R15" not in p.running()


def test_a_named_reference_on_another_date_refuses_the_new_map_steps(tmp_path, saves):
    """The transplant copies the new regions' people as the reference has them; a reference named by hand on
    another date would bring the wrong generation, so the plan refuses before anything runs."""
    wrong = ref_save(tmp_path, "Wrong.ck3", date=b"1066.9.15")
    p = transplant_plan(tmp_path, saves, reference=str(wrong))
    why = "the reference save is dated 1066.9.15, the save 987.10.27: the new map's regions would be copied from " \
          "the wrong moment"
    assert why in p.refusals
    assert "ck3update reference-mod" in p.fixes[why]["fix"] and "--transplant off" in p.fixes[why]["fix"]


def test_a_named_reference_on_another_date_is_fine_for_religion_alone(tmp_path, saves):
    wrong = ref_save(tmp_path, "Wrong.ck3", date=b"1066.9.15")
    p = transplant_plan(tmp_path, saves, reference=str(wrong), transplant="off")
    assert not any("would be copied from the wrong moment" in r for r in p.refusals)
    assert "R8" in p.running()                                     # the religion rules still use it


def test_a_named_reference_on_the_campaign_date_is_not_refused(tmp_path, saves):
    p = transplant_plan(tmp_path, saves, reference=str(ref_save(tmp_path, "Right.ck3")))
    assert not any("would be copied from the wrong moment" in r for r in p.refusals)
    assert {"R14", "R16", "R17"} <= set(p.running())


def test_with_the_switch_on_and_no_reference_the_steps_are_given(tmp_path, saves):
    p = transplant_plan(tmp_path, saves, reference="none", transplant="auto", old_game_dir=str(tmp_path / "old"))
    assert not set(PL.TRANSPLANT) & set(p.running())
    assert any("needs a reference save to load in 1.20" in n for n in p.notes)
    r15 = next(s for s in p.steps if s.id == "R15")
    assert r15.reason == "needs R14, R16, which are skipped"        # never refused later as a missing prerequisite
    assert "ck3update reference-mod" in "\n".join(p.lines())


def test_the_switch_from_the_config_and_the_config_keeps_every_key(tmp_path, saves):
    config.write_config({"disabled": ["R21"], "pack_dirs": ["D:/p"], "trusted": {"x": "h"}, "transplant": "auto"})
    config.write_disabled(["R21", "R20"])
    assert config.transplant_mode() == "auto" and config.read_config()["pack_dirs"] == ["D:/p"]
    assert config.trusted_packs() == {"x": "h"}
    p = transplant_plan(tmp_path, saves, reference=str(ref_save(tmp_path, "Ref.ck3")))
    assert {"R14", "R16"} <= set(p.running())


# --------------------------------------------------------------------------- the plan status prints is the plan update runs
def test_status_and_update_still_share_one_plan(tmp_path, saves, capsys):
    flag_pack("beidh", "B1", '\n[applies]\ncampaign = { name = "Beidh", seed = 111 }\n')
    s, g = old_save(saves), str(game(tmp_path))
    r = str(ref_save(tmp_path, "Ref.ck3"))
    assert run(capsys, "status", str(s), "--game-dir", g, "--reference", r)[0] == 0
    assert run(capsys, "update", str(s), "--game-dir", g, "--reference", r, "--no-lint",
               "--wos-shape", "faith")[0] == 0
    assert cli.LAST_PLAN["update"].as_dict() == cli.LAST_PLAN["status"].as_dict()
    assert cli.LAST_PLAN["ran"] == cli.LAST_PLAN["status"].running() and "B1" in cli.LAST_PLAN["ran"]
    assert b"B1_flag=yes" in sf.read_save(saves / "Campaign__updated__1.20.1.2.ck3").meta
