"""Tests for the transplant engine (transplant.py) and R14 + R17 (rules/transplant_1_20.py), on synthetic saves.

The scenario: the save knows k_old > d_old, k_lone and two coats; the reference adds d_new under k_old (a seam into
an existing list), c_new under d_new, d_child under k_lone (a seam that creates the list), a runtime x_ title, a new
province, and their coats. Nothing here needs the gitignored real data.
"""

from __future__ import annotations

import re
from pathlib import Path

from ck3_save_migrator import gamestate as gs
from ck3_save_migrator import rules as R
from ck3_save_migrator import savefile as sf
from ck3_save_migrator import translate as T
from ck3_save_migrator.transplant import Transplant
from tests.fixtures.make_ck3 import DEFAULT_META, build_ck3
from tests.test_translate import char, culture, gamestate, title

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


def test_r17_carries_a_company_for_its_carried_county_and_renumbers_a_taken_x_key(tmp_path):
    """A mercenary company points at its home county and nothing points at it: it comes when its county does, with
    its own x_mc_ title. Runtime x_ keys are numbered per save, so a key the campaign already has takes the next
    free number of its prefix (e2e 2026-10-26: x_mc_6 named both 12116 and 30389). A company whose county stays
    behind is not carried."""
    mc = "mercenary_company_manager={\n\tmercenary_companies={\n%s\t}\n}\n"
    save_body = gamestate(
        living=char(40),
        titles=title(0, "k_old", "\tde_jure_vassals={ 1 }\n\tcoat_of_arms_id=0\n") + title(1, "d_old", "\tde_jure_liege=0\n")
        + title(2, "k_lone", "") + title(3, "x_mc_1", "") + title(4, "x_mc_7", ""),
        coa="0={\n\tpattern=\"a\"\n}\n5={\n\tpattern=\"b\"\n}\n", coa_next=6, title_index=5,
        extra="provinces={\n1={\n\tholding={\n\t\ttype=\"castle_holding\"\n\t}\n}\n2={\n}\n}\n" + mc % "",
    )
    # the companies: 0 lives in c_new (carried), 1 in d_old (the campaign's): only 0 comes
    # x_mc_1 is led by its captain, person 11, who must come with it (soak 2026-10-26: unheld company titles)
    titles9 = title(9, "x_mc_1", "\tholder=11\n") + title(10, "x_mc_2", "")
    ref = REF.replace(b"8={\n\tkey=d_landless\n}\n", b"8={\n\tkey=d_landless\n}\n" + titles9.encode(), 1)
    ref = ref.replace(b'9={\n\tfirst_name="P9"\n}\n', b'9={\n\tfirst_name="P9"\n}\n' + char(11).encode(), 1)
    assert titles9.encode() in ref and char(11).encode() in ref
    ref += (mc % "\t\t0={\n\t\t\ttitle=9\n\t\t\tcounty=3\n\t\t}\n\t\t1={\n\t\t\ttitle=10\n\t\t\tcounty=1\n\t\t}\n").encode()
    save = sf.parse_save(build_ck3(meta=DEFAULT_META, body=save_body))
    ctx = R.RuleContext(reference=tmp_path / "ref.ck3")
    ctx.state["reference_gamestate"] = DEFAULT_META + ref
    res = {r.id: r for r in R.run_rules(save, R.select("R14"), ctx)}
    ex = res["R17"].extra
    assert ex["owner_carried"] == {"mercenary": 1, "captain": 1}
    assert ex["runtime_keys_renamed"] == {"x_mc_1": "x_mc_8"}          # past the campaign's highest, x_mc_7
    t = titles_by_key(save.gamestate)
    assert {"x_mc_1", "x_mc_7", "x_mc_8"} <= set(t) and "x_mc_2" not in t
    assert b"holder=52" in t["x_mc_8"][1]                              # the captain 11 -> 11 + (save max 40 + 1)
    assert 52 in {i for i, _ in T.entries(save.gamestate, "living")}
    g = save.gamestate
    b = gs.locate(g, "mercenary_company_manager/mercenary_companies")
    comps = [g[e.start:e.end] for e in gs.iter_entries(g, *b.body)]
    assert len(comps) == 1
    assert f"title={t['x_mc_8'][0]}".encode() in comps[0] and f"county={t['c_new'][0]}".encode() in comps[0]


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


def test_r17_registers_carried_game_start_objects_and_their_coat_names(tmp_path):
    """The game-start lists (template_cultures, static_dynasties, static_dynasty_houses) name every object the game
    made from its definitions; a carried one the reference lists is appended, a joined one is not (it is the
    campaign's already). The coat name map gains the carried coats' names; a name the campaign has keeps its coat
    (census defects 5-8, 2026-10-26)."""
    ref = (REF.replace(b'9={\n\tfirst_name="P9"\n}\n', b'9={\n\tfirst_name="P9"\n\tculture=1\n\tdynasty_house=3\n}\n', 1)
           .replace(b"culture_manager={\n\tcultures={\n", b"culture_manager={\n\ttemplate_cultures={ 0 1 }\n\tcultures={\n"
                    + culture(0, "irish").encode() + culture(1, "han").encode(), 1)
           .replace(b"dynasties={\n\tdynasty_house={\n", b"dynasties={\n\tstatic_dynasties={ 2 }\n"
                    b"\tstatic_dynasty_houses={ 3 }\n\tdynasty_house={\n3={\n\tkey=\"house_x\"\n\tdynasty=2\n}\n", 1)
           .replace(b"\tdynasties={\n\t}", b"\tdynasties={\n2={\n\tkey=2000\n\tcoat_of_arms_id=9\n}\n\t}", 1)
           .replace(b"coat_of_arms={\n\tcoat_of_arms_manager_database={\n", b"coat_of_arms={\n"
                    b"\tcoat_of_arms_manager_name_map={\n\t\tk_old=0\n\t\td_new=7\n\t\t2000=9\n\t}\n"
                    b"\tcoat_of_arms_manager_database={\n9={\n\tpattern=\"d\"\n}\n", 1))
    assert ref.count(b"template_cultures") == ref.count(b"static_dynasties") == ref.count(b"2000=9") == 1
    body = (SAVE.replace(b"culture_manager={\n\tcultures={\n", b"culture_manager={\n\ttemplate_cultures={ 0 }\n"
                         b"\tcultures={\n" + culture(0, "irish").encode(), 1)
            .replace(b"dynasties={\n\tdynasty_house={\n", b"dynasties={\n\tstatic_dynasties={ }\n"
                     b"\tstatic_dynasty_houses={ }\n\tdynasty_house={\n", 1)
            .replace(b"coat_of_arms={\n", b"coat_of_arms={\n\tcoat_of_arms_manager_name_map={\n\t\tk_old=0\n\t}\n", 1))
    save = sf.parse_save(build_ck3(meta=DEFAULT_META, body=body))
    ctx = R.RuleContext(reference=tmp_path / "ref.ck3")
    ctx.state["reference_gamestate"] = DEFAULT_META + ref
    res = {r.id: r for r in R.run_rules(save, R.select("R14,R16"), ctx)}
    ex = res["R17"].extra
    assert ex["registered"] == {"culture_manager/template_cultures": 1, "dynasties/static_dynasties": 1,
                                "dynasties/static_dynasty_houses": 1}
    assert ex["name_map_added"] == {"title": 1, "other": 1}
    g = save.gamestate

    def ids(path):
        b = gs.locate(g, path)
        return [int(x) for x in g[b.open + 1:b.close].split()]

    def id_of(path, needle):
        return next(i for i, e in T.entries(g, path) if needle in g[e.start:e.end])

    han, dyn, house = (id_of("culture_manager/cultures", b'"han"'), id_of("dynasties/dynasties", b"key=2000"),
                       id_of("dynasties/dynasty_house", b'"house_x"'))
    assert ids("culture_manager/template_cultures") == [0, han]          # irish joined: listed once
    assert ids("dynasties/static_dynasties") == [dyn] and ids("dynasties/static_dynasty_houses") == [house]
    nm = gs.locate(g, "coat_of_arms/coat_of_arms_manager_name_map")
    names = dict(re.findall(rb"([^\s={}]+)=(\d+)", g[nm.open + 1:nm.close]))
    t = titles_by_key(g)
    d_new_coat = re.search(rb"coat_of_arms_id=(\d+)", t["d_new"][1]).group(1)
    dyn_coat = re.search(rb"coat_of_arms_id=(\d+)", g[dict(T.entries(g, "dynasties/dynasties"))[dyn].start:
                                                      dict(T.entries(g, "dynasties/dynasties"))[dyn].end]).group(1)
    assert names == {b"k_old": b"0", b"d_new": d_new_coat, b"2000": dyn_coat}


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
