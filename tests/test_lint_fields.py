"""lint's carried-fields check (lint.check_reference_fields): a migrated entry carries the fields the game's own
entries of that kind carry. Finding F25 (2026-11-16): the carried custom faith had no faith_type, so event text naming
its god printed a blank."""

from __future__ import annotations

import pytest

from ck3_save_migrator import baselines as B
from ck3_save_migrator import lint as L

META = b'meta_data={\n\tsave_game_version=18\n\tversion="1.20.1.2"\n}\n'


def faith(i: int, ftype: str | None = "christian_faith", extra: str = "") -> str:
    t = f"\t\t\tfaith_type={ftype}\t\t\treligion=0\n" if ftype is not None else "\t\t\treligion=0\n"
    return f"\t\t{i}={{\n{t}\t\t\tname=\"F{i}\"\n{extra}\t\t}}\n"


def save(*faiths: str, meta: bytes = META, rites: int = 0) -> bytes:
    rite_block = ("rites={\n\tdatabase={\n" + "".join(f"\t\t{i}={{\n\t\t\tfaith={i}\n\t\t}}\n" for i in range(rites))
                  + "\t}\n}\n") if rites else ""
    return meta + ("faiths={\n\tdatabase={\n" + "".join(faiths) + "\t}\n}\n" + rite_block).encode()


def run(g: bytes, reference: bytes | None = None) -> L.LintReport:
    rep = L.LintReport()
    L.check_reference_fields(g, rep, reference)
    return rep


def finding(rep: L.LintReport, check_start: str):
    return next((f for f in rep.findings if f.check.startswith(check_start)), None)


REF = save(*(faith(i) for i in range(30)))


def test_a_faith_without_faith_type_is_named_with_what_it_costs_the_player():
    rep = run(save(*(faith(i) for i in range(29)), faith(29, None)), REF)
    f = finding(rep, "entries carry the fields")
    assert f is not None and f.severity == "warn" and f.count == 1
    assert "faiths/database: 1 of 30 lack `faith_type`" in f.examples[0] and "e.g. 29" in f.examples[0]
    assert "event text that names the faith's god shows a blank" in f.examples[0]


def test_an_empty_faith_type_is_a_gap_too():
    # the game's own re-save wrote faith_type="" for the faith the update left without one
    rep = run(save(*(faith(i) for i in range(29)), faith(29, '""')), REF)
    assert "missing 0, empty 1" in finding(rep, "entries carry the fields").examples[0]


def test_the_game_s_own_save_against_itself_has_no_gap():
    # check L2: a share the game itself leaves at 29 of 30 is not a gap in a save that matches it
    ref = save(*(faith(i) for i in range(29)), faith(29, None))
    assert finding(run(ref, ref), "entries carry the fields") is None


def test_a_field_the_game_leaves_out_of_some_entries_is_flagged_only_beyond_that_share():
    # the game leaves `extra` off 2 of 100 (98%, above the threshold); ours leaving it off 2 of 100 is normal,
    # leaving it off 30 of 100 is not
    ref = save(*(faith(i, extra="\t\t\textra=1\n" if i >= 2 else "") for i in range(100)))
    same = save(*(faith(i, extra="\t\t\textra=1\n" if i >= 2 else "") for i in range(100)))
    worse = save(*(faith(i, extra="\t\t\textra=1\n" if i >= 30 else "") for i in range(100)))
    assert finding(run(same, ref), "entries carry the fields") is None
    assert "30 of 100 lack `extra`" in finding(run(worse, ref), "entries carry the fields").examples[0]


def test_the_allowance_is_the_game_s_share_plus_three_standard_deviations_and_its_edge_passes():
    # the game leaves `extra` off 1 of 100: 1 expected in 100 of ours, allowance 1 + 3 * 1 = 4. Four of ours without
    # it is still within (mutation M2, no deviation term, 2026-11-16); five is a gap
    ref = save(*(faith(i, extra="\t\t\textra=1\n" if i >= 1 else "") for i in range(100)))
    four = save(*(faith(i, extra="\t\t\textra=1\n" if i >= 4 else "") for i in range(100)))
    five = save(*(faith(i, extra="\t\t\textra=1\n" if i >= 5 else "") for i in range(100)))
    assert finding(run(four, ref), "entries carry the fields") is None
    assert "5 of 100 lack `extra`" in finding(run(five, ref), "entries carry the fields").examples[0]


def test_a_field_left_out_on_purpose_is_info_with_its_measurement_not_a_warning():
    ref = META + (b"rites={\n\tdatabase={\n" + b"".join(b"\t\t%d={\n\t\t\trite_type=r\n\t\t}\n" % i for i in range(99))
                  + b"\t\t99={\n\t\t\tname=x\n\t\t}\n\t}\n}\n")
    ours = META + (b"rites={\n\tdatabase={\n" + b"".join(b"\t\t%d={\n\t\t\trite_type=r\n\t\t}\n" % i for i in range(90))
                   + b"".join(b"\t\t%d={\n\t\t\tname=x\n\t\t}\n" % i for i in range(90, 100)) + b"\t}\n}\n")
    rep = run(ours, ref)
    assert finding(rep, "entries carry the fields") is None
    info = finding(rep, "fields left out on purpose")
    assert info.severity == "info" and "a rite made in play has none" in info.examples[0]


def test_without_a_reference_the_shipped_baseline_for_the_save_s_version_is_the_witness():
    name, ref, base = L.field_witness(META, None)
    assert name == "the field baseline for 1.20.1.2" and ref is None and base is not None
    # the shipped baseline has 103 faiths, every one with faith_type: one of ours without it is a gap
    rep = run(save(*(faith(i) for i in range(29)), faith(29, None)))
    assert any("1 of 30 lack `faith_type`" in e for e in finding(rep, "entries carry the fields").examples)


def test_a_version_with_no_baseline_and_no_reference_is_skipped_and_says_so():
    rep = run(save(faith(0), meta=b'meta_data={\n\tversion="1.8.1"\n}\n'))
    assert rep.findings == []
    assert any("no field baseline for 1.8.1 ships with the tool" in s for s in rep.skipped)


def test_a_kind_the_witness_lacks_is_listed_as_nothing_to_compare_with_never_as_clean():
    rep = run(save(*(faith(i) for i in range(30)), rites=25), REF)
    nothing = finding(rep, "kinds of entry with nothing to compare with")
    assert nothing is not None and nothing.examples == ["rites/database"]


@pytest.mark.parametrize("fields, ran", [(True, True), (False, False)])
def test_lint_gamestate_runs_the_check_unless_told_not_to(monkeypatch, fields, ran):
    calls = []
    monkeypatch.setattr(L, "check_reference_fields", lambda g, rep, ref=None: calls.append(1))
    L.lint_gamestate(META + b"living={\n}\n", keys=False, fields=fields)
    assert bool(calls) is ran


def test_the_shipped_baseline_flags_nothing_in_a_save_shaped_like_it():
    # every field of the shipped faiths at its own share: no gap (the baseline and the check agree with each other)
    b = B.load_baseline("1.20.1.2")
    fields = [k for k, (p, e) in b["databases"]["faiths/database"]["fields"].items() if p - e >= 0.97]
    body = "".join(f"\t\t{i}={{\n" + "".join(f"\t\t\t{k}=x\n" for k in fields) + "\t\t}\n" for i in range(30))
    g = META + ("faiths={\n\tdatabase={\n" + body + "\t}\n}\n").encode()
    rep = run(g)
    gap = finding(rep, "entries carry the fields")
    assert gap is None or not any(e.startswith("faiths/database") for e in gap.examples)
