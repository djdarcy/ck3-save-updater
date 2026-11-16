"""Builder contracts (ck3_save_migrator/contracts.py): every rule that builds an entry field by field declares each
field of the game's own entries of that kind (the director's ruling, 2026-11-16, after finding F25)."""

from __future__ import annotations

import pytest

from ck3_save_migrator import baselines as B
from ck3_save_migrator import contracts as C
from ck3_save_migrator import lint as L
from ck3_save_migrator.rules import religion_1_20 as REL

BASELINE = B.load_baseline("1.20.1.2")
KINDS = sorted({c["kind"] for c in C.CONTRACTS.values() if "compare" not in c})


@pytest.mark.parametrize("kind", KINDS)
def test_every_field_of_the_game_s_own_entries_of_the_kind_is_declared(kind):
    # a new game version's new field (1.20's faith_type was one) fails here before a player sees a blank
    fields = BASELINE["databases"][kind]["fields"]
    assert C.undeclared(kind, fields) == []


def test_undeclared_names_a_field_no_contract_mentions():
    assert C.undeclared("faiths/database", ["faith_type", "a_field_from_a_new_game_version"]) == \
        ["a_field_from_a_new_game_version"]


def test_a_contract_that_cannot_be_compared_says_why_and_its_kind_is_really_absent_from_the_baseline():
    for name, c in C.CONTRACTS.items():
        if "compare" in c:
            assert c["compare"], name
            assert c["kind"] not in BASELINE["databases"], f"{name}: the baseline holds {c['kind']}; compare it"


def test_every_declaration_has_a_known_status_and_a_reason():
    for name, c in C.CONTRACTS.items():
        assert c["kind"] and c["builder"], name
        for f, (status, why) in c["fields"].items():
            assert status in C.STATUSES and why.strip(), f"{name}: {f}"


def test_lint_s_allow_list_is_the_contracts_absent_and_on_load_declarations():
    allowed = C.allowed()
    assert ("rites/database", "rite_type") in allowed and ("opinions/active_opinions", "temporary_opinion") in allowed
    assert ("faiths/database", "faith_type") not in allowed            # derived: its absence stays a warning
    # on_load declarations are allowed too (mutation M7, 2026-11-16)
    assert ("vassal_contracts/database", "liege_dynasty_date") in allowed and ("faiths/database", "tenets") in allowed
    assert L.FIELDS_ABSENT_ON_PURPOSE == allowed


# --------------------------------------------------------------------------- the vassal contract
def test_contract_entry_writes_exactly_the_fields_its_contract_says_it_carries_or_derives():
    from ck3_save_migrator._vendor.savediff import text as T
    from ck3_save_migrator.transplant import contract_entry
    decl = C.CONTRACTS["vassal contract (transplant, title lock-step)"]["fields"]
    def written(s: str) -> list[str]:
        b = s.encode()
        return [c.key.decode() for c in T.iter_children(b, b.index(b"{") + 1, b.rindex(b"}")) if c.key]
    with_group, without = contract_entry(7, 11, 22, "987.10.27", b"feudal"), contract_entry(8, 11, 22, "987.1.1", None)
    assert with_group.startswith("7={") and with_group.endswith("\t\t}")
    assert set(written(with_group)) == {f for f, (s, _) in decl.items() if s in (C.CARRIED, C.DERIVED)}
    assert "contract_group" not in written(without) and "levels={ 1 }" in without
    # an empty group is no group: never a bare contract_group= line (mutation M10, 2026-11-16)
    assert "contract_group" not in contract_entry(9, 11, 22, "987.1.1", b"")


# --------------------------------------------------------------------------- R10's eminent holy sites
def _faiths(g: bytes) -> dict:
    return REL._db(g)[1]


FAITHS = (b"faiths={\n\tdatabase={\n"
          b"\t\t12={\n\t\t\tfaith_type=christian_faith\t\t\treligion=8\n\t\t\tholy_sites={ 0 1 5 3 }\n"
          b"\t\t\teminent_holy_sites={ 0 1 5 }\n\t\t}\n"
          b"\t\t13={\n\t\t\tfaith_type=\"\"\t\t\treligion=8\n\t\t}\n"
          b"\t}\n}\nrites={\n\tdatabase={\n\t}\n}\n")


def test_eminent_holy_sites_are_the_faith_s_own_sites_its_origin_counts_as_eminent_in_its_own_order():
    assert REL._eminent_holy_sites(FAITHS, _faiths(FAITHS), "12", ["5", "9", "0"]) == ["5", "0"]


def test_eminent_holy_sites_fall_back_to_the_first_holy_site_and_never_exceed_three():
    assert REL._eminent_holy_sites(FAITHS, _faiths(FAITHS), "12", ["7", "8"]) == ["7"]      # none in common
    assert REL._eminent_holy_sites(FAITHS, _faiths(FAITHS), "99", ["7", "8"]) == ["7"]      # unknown origin
    many = FAITHS.replace(b"eminent_holy_sites={ 0 1 5 }", b"eminent_holy_sites={ 0 1 5 3 }")
    assert REL._eminent_holy_sites(many, _faiths(many), "12", ["0", "1", "5", "3"]) == ["0", "1", "5"]
    assert REL._eminent_holy_sites(FAITHS, _faiths(FAITHS), "12", []) == []


def test_faith_type_of_an_empty_or_missing_type_is_none():
    f = _faiths(FAITHS)
    assert REL._faith_type(FAITHS, f, "12") == b"christian_faith"
    assert REL._faith_type(FAITHS, f, "13") is None and REL._faith_type(FAITHS, f, "99") is None
