"""Tests for the transplant engine (transplant.py) and R14 + R17 (rules/transplant_1_20.py), on synthetic saves.

The scenario: the save knows k_old > d_old, k_lone and two coats; the reference adds d_new under k_old (a seam into
an existing list), c_new under d_new, d_child under k_lone (a seam that creates the list), a runtime x_ title, a new
province, and their coats. Nothing here needs the gitignored real data.
"""

from __future__ import annotations

from pathlib import Path

from ck3_save_migrator import gamestate as gs
from ck3_save_migrator import rules as R
from ck3_save_migrator import savefile as sf
from ck3_save_migrator import translate as T
from ck3_save_migrator.transplant import Transplant
from tests.fixtures.make_ck3 import DEFAULT_META, build_ck3
from tests.test_translate import char, gamestate, title

SAVE = gamestate(
    living=char(40),
    titles=title(0, "k_old", "\tde_jure_vassals={ 1 }\n\tcoat_of_arms_id=0\n")
    + title(1, "d_old", "\tde_jure_liege=0\n")
    + title(2, "k_lone", ""),
    coa="0={\n\tpattern=\"a\"\n}\n5={\n\tpattern=\"b\"\n}\n", coa_next=6, title_index=3,
    extra="provinces={\n1={\n\tholding={\n\t\ttype=\"castle_holding\"\n\t}\n}\n2={\n}\n}\n",
)
REF = gamestate(
    living=char(9),
    titles=title(0, "k_old", "\tde_jure_vassals={ 1 2 }\n")
    + title(1, "d_old", "\tde_jure_liege=0\n")
    + title(2, "d_new", "\tde_jure_liege=0\n\tde_jure_vassals={ 3 1 }\n\tholder=9\n\tcoat_of_arms_id=7\n")
    + title(3, "c_new", "\tde_jure_liege=2\n\tde_facto_liege=1\n\tcapital=3\n\tcoat_of_arms_id=8\n")
    + title(4, "x_x_1", "\tholder=9\n")
    + title(5, "k_lone", "")
    + title(6, "d_child", "\tde_jure_liege=5\n\tde_jure_vassals={ 7 }\n")
    + title(7, "b_child", "\tde_jure_liege=6\n")
    + title(8, "d_landless", ""),                      # unheld, no land: left to the engine
    coa="7={\n\tpattern=\"n\"\n}\n8={\n\tpattern=\"m\"\n}\n",
    extra="provinces={\n1={\n}\n2={\n}\n3={\n\tholding={\n\t\ttype=castle_holding\n\t}\n}\n}\n",
)


def run_r14(tmp_path: Path):
    save = sf.parse_save(build_ck3(meta=DEFAULT_META, body=SAVE))
    ctx = R.RuleContext(reference=tmp_path / "ref.ck3")
    ctx.state["reference_gamestate"] = DEFAULT_META + REF
    res = R.run_rules(save, R.select("R14"), ctx)
    return save, ctx, {r.id: r for r in res}


def test_r17_carries_the_county_record_of_a_carried_county(tmp_path):
    """county_manager/counties is keyed BY the county's title key: a carried county brings its record; a joined
    (campaign) county does not get the reference's (census 2026-10-26: 910 new-map counties arrived without one)."""
    cm = b"county_manager={\n\tcounties={\n%s\t}\n}\n"
    save = sf.parse_save(build_ck3(meta=DEFAULT_META, body=SAVE + cm % b""))
    ref = REF + cm % (b"\t\tc_new={\n\t\t\tdevelopment=7\n\t\t}\n\t\tk_old={\n\t\t\tdevelopment=3\n\t\t}\n")
    ctx = R.RuleContext(reference=tmp_path / "ref.ck3")
    ctx.state["reference_gamestate"] = DEFAULT_META + ref
    R.run_rules(save, R.select("R14"), ctx)
    g = save.gamestate
    b = gs.locate(g, "county_manager/counties")
    got = {e.key: g[e.start:e.end] for e in gs.iter_entries(g, *b.body)}
    assert set(got) == {b"c_new"} and b"development=7" in got[b"c_new"]


def titles_by_key(g: bytes) -> dict[str, tuple[int, bytes]]:
    out = {}
    for i, e in T.entries(g, "landed_titles/landed_titles"):
        k = T._depth0(g, e, T._KEY).decode()
        out[k] = (i, g[e.start:e.end])
    return out


def test_r14_plans_the_new_titles_and_provinces_only(tmp_path):
    _, _, res = run_r14(tmp_path)
    ex = res["R14"].extra
    assert ex["titles_planned"] == 4                    # d_new, c_new, d_child, b_child: not the save's, not x_x_1
    assert ex["by_tier"] == {"b": 1, "c": 1, "d": 2} and ex["x_titles_left_out"] == 1
    assert ex["left_to_the_engine_unheld_landless"] == 1                # d_landless
    assert ex["provinces_planned"] == 1                 # province 3


def test_r17_writes_the_titles_with_translated_ids(tmp_path):
    save, _, res = run_r14(tmp_path)
    t = titles_by_key(save.gamestate)
    assert set(t) == {"k_old", "d_old", "k_lone", "d_new", "c_new", "d_child", "b_child"}
    d_new_id, d_new = t["d_new"]
    c_new_id, c_new = t["c_new"]
    assert d_new_id == 2 + 3 and c_new_id == 3 + 3      # title base = save max index 2 + 1
    assert b"de_jure_liege=0" in d_new                  # the seam: joined to the save's k_old
    assert f"de_jure_vassals={{ {c_new_id} }}".encode() in d_new   # old d_old dropped from a new title's list
    assert b"holder" not in d_new                       # no people planned: the holder is not in the output
    assert b"de_facto_liege" not in c_new               # a new title under a campaign title de facto: dropped
    assert f"capital={c_new_id}".encode() in c_new
    assert res["R17"].extra["dropped"]["landed_titles/landed_titles | de_jure_vassals/*"] == 1
    assert res["R17"].extra["collisions"] == 0 and "title" in res["R17"].extra["collisions_by_space"]


def test_r17_stitches_seams_into_existing_and_new_lists(tmp_path):
    save, _, res = run_r14(tmp_path)
    t = titles_by_key(save.gamestate)
    assert b"de_jure_vassals={ 1 5 }" in t["k_old"][1]          # d_new (5) appended to the list
    assert f"de_jure_vassals={{ {t['d_child'][0]} }}".encode() in t["k_lone"][1]   # list created
    assert res["R17"].extra["seams"] == 2 and res["R17"].extra["seam_parents"] == 2


def test_r17_carries_coats_and_raises_the_counter(tmp_path):
    save, _, res = run_r14(tmp_path)
    t = titles_by_key(save.gamestate)
    assert b"coat_of_arms_id=13" in t["d_new"][1] and b"coat_of_arms_id=14" in t["c_new"][1]   # base 6
    coats = {i for i, _ in T.entries(save.gamestate, "coat_of_arms/coat_of_arms_manager_database")}
    assert coats == {0, 5, 13, 14}
    assert res["R17"].extra["coa_next_id"] == [6, 15]
    assert b"next_id=15" in save.gamestate


def test_r17_inserts_provinces_and_entries_at_column_zero(tmp_path):
    save, _, _ = run_r14(tmp_path)
    g = save.gamestate
    assert {i for i, _ in T.entries(g, "provinces")} == {1, 2, 3}
    for key in (b"\n3={", b"\n5={", b"\n6={", b"\n13={"):
        assert key in g                                 # every inserted entry starts a line, no indent
    gs.match_brace(g, gs.find_section(g, "landed_titles").open)   # still balanced


def test_the_campaign_entries_stay_byte_identical_apart_from_the_seams(tmp_path):
    save, _, _ = run_r14(tmp_path)
    before = titles_by_key(DEFAULT_META + SAVE)
    after = titles_by_key(save.gamestate)
    assert after["d_old"][1] == before["d_old"][1]
    assert after["k_old"][1] == before["k_old"][1].replace(b"{ 1 }", b"{ 1 5 }")


def test_r16_brings_the_holders_and_keeps_their_titles_held(tmp_path):
    save = sf.parse_save(build_ck3(meta=DEFAULT_META, body=SAVE))
    ctx = R.RuleContext(reference=tmp_path / "ref.ck3")
    ctx.state["reference_gamestate"] = DEFAULT_META + REF
    res = {r.id: r for r in R.run_rules(save, R.select("R14,R16"), ctx)}
    assert res["R16"].extra["rulers"] == 1 and res["R16"].matched == 1
    t = titles_by_key(save.gamestate)
    assert b"holder=50" in t["d_new"][1]                # character 9 -> 9 + (save max 40 + 1)
    assert 50 in {i for i, _ in T.entries(save.gamestate, "living")}


def test_a_displaced_ruler_is_placed_in_the_takers_court():
    from ck3_save_migrator.transplant import _set_employer
    has = b"5={\n\tfirst_name=\"A\"\n\tcourt_data={\n\t\temployer=9\n\t}\n}"
    court = b"5={\n\tfirst_name=\"A\"\n\tcourt_data={\n\t\thost=3\n\t}\n}"
    bare = b"5={\n\tfirst_name=\"A\"\n}"
    assert b"\t\temployer=777\n" in _set_employer(has, 777) and b"employer=9" not in _set_employer(has, 777)
    assert b"court_data={\n\t\temployer=777\n\t\thost=3" in _set_employer(court, 777)
    out = _set_employer(bare, 777)
    assert out.endswith(b"\tcourt_data={\n\t\temployer=777\n\t}\n}") and out.count(b"{") == out.count(b"}")


def test_without_a_reference_r14_skips_and_r17_has_nothing():
    save = sf.parse_save(build_ck3(meta=DEFAULT_META, body=SAVE))
    res = R.run_rules(save, R.select("R14"), R.RuleContext())
    assert "skipped" in res[0].extra and "skipped" in res[1].extra


def test_planning_refuses_nothing_joined():
    t = Transplant(DEFAULT_META + SAVE, DEFAULT_META + REF)
    t.add("title", {0, 1, 2}, "test")                   # 0 and 1 are the save's own titles (joined)
    assert t.carry["title"] == {2}
