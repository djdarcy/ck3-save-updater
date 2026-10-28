"""``--rules`` can leave a rule out: ``all,-R21``, or ``-R21`` alone for all but R21.

An exclusion applies after ``all``, the named rules and the config's disabled list; it matches an id or a name in
any case; an unknown one is refused, listing the known ids; and leaving out a rule another selected rule needs is
refused, naming both.
"""

from __future__ import annotations

import pytest

from ck3_save_migrator import cli
from ck3_save_migrator import rules as R
from tests.fixtures.make_ck3 import RULES_BODY, RULES_META, build_ck3

ALL = [r.id for r in R.select("all")]


def ids(spec: str) -> list[str]:
    return [r.id for r in R.select(spec)]


def test_all_minus_one():
    assert ids("all,-R21") == [i for i in ALL if i != "R21"]


def test_a_minus_alone_means_all_but_that_one():
    assert ids("-R21") == ids("all,-R21")
    assert ids("-R21,-R5") == [i for i in ALL if i not in ("R21", "R5")]


def test_ids_and_names_in_any_case():
    assert ids("all,-dead-liege-cycles") == ids("all,-r21") == ids("ALL, -R21") == ids("all,-R21")


def test_leaving_out_a_rule_that_was_not_selected_changes_nothing():
    assert ids("all,-R14") == ALL                                   # R14 is opt-in: not in all


def test_an_opt_in_rule_can_be_added_and_another_left_out():
    assert ids("all,R14,R16,R15,-R21") == [i for i in ids("all,R14,R16,R15") if i != "R21"]


def test_an_unknown_exclusion_is_refused_listing_the_known_ids():
    with pytest.raises(ValueError) as e:
        R.select("all,-R99")
    assert "unknown rule '-R99'" in str(e.value) and "R21=dead-liege-cycles" in str(e.value)


def test_leaving_out_a_requirement_is_refused_naming_both():
    with pytest.raises(ValueError) as e:
        R.select("all,-R8")
    assert "leaves out R8" in str(e.value) and "R10 (custom-faith) requires" in str(e.value)
    assert ids("all,-R12,-R9,-R10,-R8") == [i for i in ALL if i not in ("R8", "R9", "R10", "R12")]


def test_leaving_out_the_transplant_write_step_is_refused_naming_both():
    with pytest.raises(ValueError, match=r"leaves out R17 \(transplant-write\), which R1[456] needs"):
        R.select("all,R14,R16,R15,-R17")


def test_a_rule_both_named_and_left_out_is_refused():
    with pytest.raises(ValueError, match=r"R21 is both named and left out"):
        R.select("R21,-R21")


def test_an_empty_selection_is_still_refused():
    with pytest.raises(ValueError, match="empty rule selection"):
        R.select(" ")


# --------------------------------------------------------------------------- through the command line
def ran(out: str) -> list[str]:
    return [ln.split()[0] for ln in out.splitlines() if ln.startswith("    R")]


def test_migrate_leaves_the_rule_out(tmp_path, capsys):
    src = tmp_path / "My_Old_Campaign.ck3"
    src.write_bytes(build_ck3(meta=RULES_META, body=RULES_BODY))
    assert cli.main(["migrate", str(src), "--rules", "-R21", "--no-lint", "-o", str(tmp_path / "o.ck3")]) == 0
    out = capsys.readouterr().out
    assert "R21" not in ran(out) and "R5" in ran(out)


def test_the_exclusion_applies_after_the_config(tmp_path, capsys):
    assert cli.main(["disable", "R5"]) == 0
    capsys.readouterr()
    src = tmp_path / "My_Old_Campaign.ck3"
    src.write_bytes(build_ck3(meta=RULES_META, body=RULES_BODY))
    assert cli.main(["migrate", str(src), "--rules", "all,-R21", "--no-lint", "-o", str(tmp_path / "o.ck3")]) == 0
    out = capsys.readouterr().out
    assert "skipped by your config: R5" in out
    assert "R21" not in ran(out) and "R5" not in ran(out) and "R1" in ran(out)


def test_check_takes_the_exclusion_too(tmp_path, capsys):
    src = tmp_path / "My_Old_Campaign.ck3"
    src.write_bytes(build_ck3(meta=RULES_META, body=RULES_BODY))
    assert cli.main(["check", str(src), "--rules", "all,-R1"]) == 0
    out = capsys.readouterr().out
    listed = [ln.split()[0] for ln in out.splitlines() if ln.startswith("  R")]
    assert "R1" not in listed and "R4" in listed


def test_a_minus_value_after_rules_is_read_as_its_value():
    assert cli.join_rules_value(["migrate", "s.ck3", "--rules", "-R21", "-o", "x"]) == \
        ["migrate", "s.ck3", "--rules=-R21", "-o", "x"]
    assert cli.join_rules_value(["check", "s.ck3", "--rules", "all,-R21"]) == ["check", "s.ck3", "--rules", "all,-R21"]
    assert cli.join_rules_value(["migrate", "s", "--rules", "--force"]) == ["migrate", "s", "--rules", "--force"]


def test_from_a_shell_rules_minus_works(tmp_path):
    import subprocess
    import sys
    src = tmp_path / "My_Old_Campaign.ck3"
    src.write_bytes(build_ck3(meta=RULES_META, body=RULES_BODY))
    r = subprocess.run([sys.executable, "-m", "ck3_save_migrator", "check", str(src), "--rules", "-R1"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    listed = [ln.split()[0] for ln in r.stdout.splitlines() if ln.startswith("  R")]
    assert "R1" not in listed and "R4" in listed


def test_migrate_refuses_an_unknown_exclusion_with_exit_1(tmp_path, capsys):
    src = tmp_path / "My_Old_Campaign.ck3"
    src.write_bytes(build_ck3(meta=RULES_META, body=RULES_BODY))
    assert cli.main(["migrate", str(src), "--rules", "all,-nope", "--no-lint", "-o", str(tmp_path / "o.ck3")]) == 1
    assert "unknown rule '-nope'" in capsys.readouterr().err and not (tmp_path / "o.ck3").exists()
