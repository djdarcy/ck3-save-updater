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
    + title(8, "d_landless", ""),                      # unheld, no land: carried empty, as a fresh game has it
    coa="7={\n\tpattern=\"n\"\n}\n8={\n\tpattern=\"m\"\n}\n",
    extra="provinces={\n1={\n}\n2={\n}\n3={\n\tholding={\n\t\ttype=castle_holding\n\t}\n}\n}\n",
)


def migrate(tmp_path: Path, save_body: bytes, ref_body: bytes, rules: str = "R14,R16", **ctx_kw):
    """Run ``rules`` on a synthetic save with a synthetic same-date reference: (the migrated save, {id: result}).
    ``ctx_kw`` goes to the RuleContext (game_dir=, expansion_orders=)."""
    save = sf.parse_save(build_ck3(meta=DEFAULT_META, body=save_body))
    ctx = R.RuleContext(reference=tmp_path / "ref.ck3", **ctx_kw)
    ctx.state["reference_gamestate"] = DEFAULT_META + ref_body
    return save, {r.id: r for r in R.run_rules(save, R.select(rules), ctx)}


def run_r14(tmp_path: Path):
    return migrate(tmp_path, SAVE, REF, "R14")


def bodies(g: bytes, path: str) -> dict[int, bytes]:
    """id -> entry bytes of a database (``living``, ``provinces``, ...)."""
    return {i: g[e.start:e.end] for i, e in T.entries(g, path)}


def test_r17_carries_the_county_record_of_a_carried_county(tmp_path):
    """county_manager/counties is keyed BY the county's title key: a carried county brings its record; a joined
    (campaign) county does not get the reference's (census 2026-10-26: 910 new-map counties arrived without one)."""
    cm = b"county_manager={\n\tcounties={\n%s\t}\n}\n"
    ref = REF + cm % (b"\t\tc_new={\n\t\t\tdevelopment=7\n\t\t}\n\t\tk_old={\n\t\t\tdevelopment=3\n\t\t}\n")
    save, _ = migrate(tmp_path, SAVE + cm % b"", ref, "R14")
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
    save, res = migrate(tmp_path, save_body, ref, "R14")
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


def test_r17_registers_a_carried_runtime_title_in_dynamic_templates(tmp_path):
    """1.20 rejects an x_ title key missing from landed_titles/dynamic_templates and destroys the title in play,
    leaving its company dangling, which crashed the founding save after a New Year (2026-10-27). A carried company's
    title is registered under its output key, with the reference's own entry; the campaign's entries stay."""
    mc = "mercenary_company_manager={\n\tmercenary_companies={\n%s\t}\n}\n"
    dt = '\tdynamic_templates={ %s }\n'
    save_body = gamestate(
        living=char(40),
        titles=title(0, "k_old", "\tde_jure_vassals={ 1 }\n\tcoat_of_arms_id=0\n") + title(1, "d_old", "\tde_jure_liege=0\n")
        + title(2, "k_lone", "") + title(3, "x_mc_1", "") + title(4, "x_mc_7", ""),
        coa="0={\n\tpattern=\"a\"\n}\n5={\n\tpattern=\"b\"\n}\n", coa_next=6, title_index=5,
        extra="provinces={\n1={\n\tholding={\n\t\ttype=\"castle_holding\"\n\t}\n}\n2={\n}\n}\n" + mc % "",
    )
    save_body = save_body.replace(b"landed_titles={\n", b"landed_titles={\n" + (dt % '{ key="x_mc_1" tier=duchy dyn=yes } '
                                  '{ key="x_mc_7" tier=duchy dyn=yes }').encode(), 1)
    titles9 = title(9, "x_mc_1", "\tholder=11\n") + title(10, "x_mc_2", "")
    ref = REF.replace(b"8={\n\tkey=d_landless\n}\n", b"8={\n\tkey=d_landless\n}\n" + titles9.encode(), 1)
    ref = ref.replace(b'9={\n\tfirst_name="P9"\n}\n', b'9={\n\tfirst_name="P9"\n}\n' + char(11).encode(), 1)
    ref += (mc % "\t\t0={\n\t\t\ttitle=9\n\t\t\tcounty=3\n\t\t}\n").encode()
    ref = ref.replace(b"landed_titles={\n", b"landed_titles={\n" + (dt % '{ key="x_mc_1" tier=duchy dyn=yes } '
                      '{ key="x_mc_2" tier=duchy dyn=yes }').encode(), 1)
    save, res = migrate(tmp_path, save_body, ref, "R14")
    assert res["R17"].extra["runtime_keys_renamed"] == {"x_mc_1": "x_mc_8"}
    g = save.gamestate
    b = gs.locate(g, "landed_titles/dynamic_templates")
    reg = re.findall(rb'key="([^"]+)"([^}]*)\}', g[b.open:b.close])
    assert [k for k, _ in reg] == [b"x_mc_1", b"x_mc_7", b"x_mc_8"]          # the campaign's two, then the carried
    assert b"tier=duchy" in reg[2][1] and b"dyn=yes" in reg[2][1]
    assert res["R17"].extra["registered"]["landed_titles/dynamic_templates"] == 1


def titles_by_key(g: bytes) -> dict[str, tuple[int, bytes]]:
    out = {}
    for i, e in T.entries(g, "landed_titles/landed_titles"):
        k = T._depth0(g, e, T._KEY).decode()
        out[k] = (i, g[e.start:e.end])
    return out


def test_r14_plans_the_new_titles_and_provinces_only(tmp_path):
    _, res = run_r14(tmp_path)
    ex = res["R14"].extra
    assert ex["titles_planned"] == 5        # d_new, c_new, d_child, b_child, d_landless: not the save's, not x_x_1
    assert ex["by_tier"] == {"b": 1, "c": 1, "d": 3} and ex["x_titles_left_out"] == 1
    assert ex["unheld_titular_carried"] == 1 and ex["left_to_the_engine"] == []      # d_landless is carried
    assert ex["provinces_planned"] == 1                 # province 3


def test_r14_carries_an_unheld_titular_title_empty_but_not_one_the_engine_creates(tmp_path):
    """2026-10-27 (DWP 05-49-04, option B): a fresh 1.20 game keeps empty records for the titles nobody holds yet
    (h_roman_empire, the monastic orders); scripts name them, and the engine created 1 of 323 in 16 years of play.
    So they are carried, empty as the reference has them -- nobody is handed a title (djdarcy: "we don't want to
    create titles that weren't meant to be used or that players need to earn"). A title the engine is measured to
    create itself (d_knights_hospitaller) is left to it, or the load logs a duplicate (2026-10-25)."""
    hosp = title(20, "d_knights_hospitaller", "\tdate=9999.1.1\n")
    ref = REF.replace(b"8={\n\tkey=d_landless\n}\n", b"8={\n\tkey=d_landless\n\tdate=9999.1.1\n}\n" + hosp.encode(), 1)
    save, res = migrate(tmp_path, SAVE, ref, "R14")
    t = titles_by_key(save.gamestate)
    assert "d_landless" in t and b"holder" not in t["d_landless"][1]     # carried, held by nobody
    assert b"date=9999.1.1" in t["d_landless"][1]                       # in the reference's never-created state
    assert "d_knights_hospitaller" not in t                             # the engine makes its own
    ex = res["R14"].extra
    assert ex["left_to_the_engine"] == ["d_knights_hospitaller"] and ex["unheld_titular_carried"] == 1
    ref_keys = set(titles_by_key(DEFAULT_META + ref))
    assert set(t) <= ref_keys | {"k_old", "d_old", "k_lone"}            # nothing the reference lacks is created


def test_r15_held_title_successors_go_to_the_campaign_holder(tmp_path):
    """djdarcy 2026-10-27: "any titles that were in play that are still existent in the game that were present in
    our original game should be upgraded if possible so the correct holder still has their title." A held title
    R15 removed because 1.20 split it (recorded as ctx.state["r15_kept"]) hands its successor to the campaign holder,
    not the reference's: the holder gains it in his domain (made when he has none), and as his only title it takes
    the old title's de facto liege. The report names the title, its origin and the displaced ruler."""
    save = sf.parse_save(build_ck3(meta=DEFAULT_META, body=SAVE))
    ctx = R.RuleContext(reference=tmp_path / "ref.ck3")
    ctx.state["reference_gamestate"] = DEFAULT_META + REF
    ctx.state["r15_kept"] = [{"key": "d_gone", "holder": 40, "successors": ["d_new"], "old_liege_key": "k_old"}]
    res = {r.id: r for r in R.run_rules(save, R.select("R14"), ctx)}
    t = titles_by_key(save.gamestate)
    d_new_id, d_new = t["d_new"]
    assert b"holder=40" in d_new and b"de_facto_liege=0" in d_new      # the campaign holder; k_old as liege
    living = bodies(save.gamestate, "living")
    assert f"domain={{ {d_new_id} }}".encode() in living[40]            # landed_data made for him
    (row,) = res["R17"].extra["kept_by_holder"]
    assert row["title"] == "d_new" and row["from"] == "d_gone" and row["holder"] == 40 and row["liege"] == "k_old"
    assert res["R17"].extra["kept_skipped"] == []


def _kept(tmp_path, save_body, ref_body, kept, rules="R14"):
    save = sf.parse_save(build_ck3(meta=DEFAULT_META, body=save_body))
    ctx = R.RuleContext(reference=tmp_path / "ref.ck3")
    ctx.state["reference_gamestate"] = DEFAULT_META + ref_body
    ctx.state["r15_kept"] = kept
    return save, {r.id: r for r in R.run_rules(save, R.select(rules), ctx)}


def test_r15_held_title_takes_its_holders_contract_liege_when_the_old_liege_is_gone(tmp_path):
    """play5 (2026-10-27) crashed at 989.1.1: c_tengger went back to its campaign holder with no de facto liege
    while his vassal contract still bound him to his liege. A holder bound by a contract takes that liege's primary
    title as his regained primary's liege, when the old liege title is gone from the save."""
    save_body = gamestate(
        living=char(40) + char(41, "\tlanded_data={\n\t\tdomain={ 0 }\n\t\tvassal_contracts={ 0 }\n\t}\n"),
        titles=title(0, "k_old", "\tholder=41\n\tde_jure_vassals={ 1 }\n") + title(1, "d_old", "\tde_jure_liege=0\n"),
        title_index=2,
        extra="provinces={\n1={\n}\n}\nvassal_contracts={\n\tactive={\n\t\t0={\n\t\t\tvassal=40\n\t\t\tliege=41\n"
              "\t\t}\n\t}\n}\n",
    )
    save, res = _kept(tmp_path, save_body, REF,
                      [{"key": "d_gone", "holder": 40, "successors": ["d_new"], "old_liege_key": None}])
    t = titles_by_key(save.gamestate)
    assert b"holder=40" in t["d_new"][1] and b"de_facto_liege=0" in t["d_new"][1]     # under 41's k_old
    assert res["R17"].extra["kept_relinked"][0]["why"] == "his contract's liege"


def test_r15_displaced_rulers_own_title_skips_the_handed_back_liege(tmp_path):
    """play5: the copied ruler who held d_langshan kept c_tiande under it; with d_langshan handed back, c_tiande
    made him a vassal of the campaign holder with no contract. His title takes the liege above the handed-back one
    (here d_new's own de facto liege, the carried d_landless)."""
    ref = REF.replace(b"\tholder=9\n\tcoat_of_arms_id=7\n", b"\tholder=9\n\tde_facto_liege=8\n\tcoat_of_arms_id=7\n", 1)
    ref = ref.replace(b"\tde_facto_liege=1\n\tcapital=3\n", b"\tholder=9\n\tde_facto_liege=2\n\tcapital=3\n", 1)
    assert b"de_facto_liege=8" in ref and b"de_facto_liege=2" in ref
    save, res = _kept(tmp_path, SAVE, ref,
                      [{"key": "d_gone", "holder": 40, "successors": ["d_new"], "old_liege_key": None}], "R14,R16")
    t = titles_by_key(save.gamestate)
    assert b"holder=40" in t["d_new"][1]
    c_new = t["c_new"][1]
    assert int(re.search(rb"holder=(\d+)", c_new).group(1)) != 40                    # still the copied ruler's
    assert f"de_facto_liege={t['d_landless'][0]}".encode() in c_new                   # not d_new, now 40's
    assert any(r["title"] == "c_new" for r in res["R17"].extra["kept_relinked"])


def test_r15_baron_contract_follows_the_county_holder(tmp_path):
    """play5: b_taihe went back to its campaign baron, but its county had gone to another campaign ruler while the
    baron's contract still named his old liege. A barony's liege is always its county, so the contract follows:
    its liege becomes the county's holder, and it leaves the old liege's list for the new one's."""
    save_body = gamestate(
        living=char(40) + char(41, "\tlanded_data={\n\t\tdomain={ 0 }\n\t\tvassal_contracts={ 0 }\n\t}\n") + char(42),
        titles=title(0, "k_old", "\tholder=41\n\tde_jure_vassals={ 1 }\n") + title(1, "d_old", "\tde_jure_liege=0\n"),
        title_index=2,
        extra="provinces={\n1={\n}\n}\nvassal_contracts={\n\tactive={\n\t\t0={\n\t\t\tvassal=40\n\t\t\tliege=41\n"
              "\t\t}\n\t}\n}\n",
    )
    ref = REF.replace(b"8={\n\tkey=d_landless\n}\n",
                      b"8={\n\tkey=d_landless\n}\n9={\n\tkey=b_new\n\tde_jure_liege=3\n\tholder=9\n}\n", 1)
    ref = ref.replace(b"\tde_facto_liege=1\n\tcapital=3\n", b"\tholder=9\n\tcapital=3\n", 1)
    save, res = _kept(tmp_path, save_body, ref,
                      [{"key": "c_gone", "holder": 42, "successors": ["c_new"], "old_liege_key": None},
                       {"key": "b_gone", "holder": 40, "successors": ["b_new"], "old_liege_key": None}])
    g = save.gamestate
    t = titles_by_key(g)
    assert b"holder=42" in t["c_new"][1] and b"holder=40" in t["b_new"][1]
    c = gs.locate(g, "vassal_contracts/active")
    assert b"liege=42" in g[c.open:c.close] and b"liege=41" not in g[c.open:c.close]
    living = bodies(g, "living")
    assert re.search(rb"vassal_contracts=\{\s*\}", living[41])
    assert re.search(rb"vassal_contracts=\{\s*0\s*\}", living[42])


def test_r15_scopes_naming_the_removed_title_name_its_successor(tmp_path):
    """2026-10-27: the hand-back left 113 stored scopes (character variables like ``title1``) naming the held titles
    R15 removed. djdarcy: "if it does make sense for us to remap to keep events active that were active before it
    might be worth a check to see if we can migrate successfully so we don't break old quests". A scope that names
    the removed title (save id 9 here, gone from the output) names the successor its holder regained; a scope that
    names a live title is left alone."""
    var = ("\tvariables={\n\t\tdata={ {\n\t\t\t\tflag=\"title1\"\n\t\t\t\tdata={\n\t\t\t\t\ttype=lt\n"
           "\t\t\t\t\tidentity=99\n\t\t\t\t}\n\t\t\t}\n {\n\t\t\t\tflag=\"home\"\n\t\t\t\tdata={\n\t\t\t\t\ttype=lt\n"
           "\t\t\t\t\tidentity=0\n\t\t\t\t}\n\t\t\t}\n }\n\t}\n")
    save_body = SAVE.replace(char(40).encode(), (char(40) + char(41, var)).encode(), 1)
    assert b"identity=99" in save_body
    save, res = _kept(tmp_path, save_body, REF,
                      [{"key": "d_gone", "holder": 40, "successors": ["d_new"], "old_liege_key": "k_old", "id": 99}])
    t = titles_by_key(save.gamestate)
    living = bodies(save.gamestate, "living")
    assert f"identity={t['d_new'][0]}".encode() in living[41]        # title1 now names d_new
    assert b"identity=99" not in living[41] and b"identity=0" in living[41]  # the live k_old scope untouched
    assert res["R17"].extra["kept_scopes_remapped"] == {"scopes": 1, "titles": {"d_gone": 1}}


def test_r15_held_title_successor_not_in_the_reference_is_skipped_and_named(tmp_path):
    save = sf.parse_save(build_ck3(meta=DEFAULT_META, body=SAVE))
    ctx = R.RuleContext(reference=tmp_path / "ref.ck3")
    ctx.state["reference_gamestate"] = DEFAULT_META + REF
    ctx.state["r15_kept"] = [{"key": "d_gone", "holder": 40, "successors": ["d_nowhere"], "old_liege_key": None}]
    res = {r.id: r for r in R.run_rules(save, R.select("R14"), ctx)}
    assert res["R17"].extra["kept_skipped"] == [{"title": "d_nowhere", "from": "d_gone", "why": "not in the reference"}]
    assert b"holder=40" not in save.gamestate


def test_r17_writes_the_titles_with_translated_ids(tmp_path):
    save, res = run_r14(tmp_path)
    t = titles_by_key(save.gamestate)
    assert set(t) == {"k_old", "d_old", "k_lone", "d_new", "c_new", "d_child", "b_child", "d_landless"}
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
    save, res = run_r14(tmp_path)
    t = titles_by_key(save.gamestate)
    assert b"de_jure_vassals={ 1 5 }" in t["k_old"][1]          # d_new (5) appended to the list
    assert f"de_jure_vassals={{ {t['d_child'][0]} }}".encode() in t["k_lone"][1]   # list created
    assert res["R17"].extra["seams"] == 2 and res["R17"].extra["seam_parents"] == 2


def test_r17_carries_coats_and_raises_the_counter(tmp_path):
    save, res = run_r14(tmp_path)
    t = titles_by_key(save.gamestate)
    assert b"coat_of_arms_id=13" in t["d_new"][1] and b"coat_of_arms_id=14" in t["c_new"][1]   # base 6
    coats = {i for i, _ in T.entries(save.gamestate, "coat_of_arms/coat_of_arms_manager_database")}
    assert coats == {0, 5, 13, 14}
    assert res["R17"].extra["coa_next_id"] == [6, 15]
    assert b"next_id=15" in save.gamestate


def test_r17_inserts_provinces_and_entries_at_column_zero(tmp_path):
    save, _ = run_r14(tmp_path)
    g = save.gamestate
    assert {i for i, _ in T.entries(g, "provinces")} == {1, 2, 3}
    for key in (b"\n3={", b"\n5={", b"\n6={", b"\n13={"):
        assert key in g                                 # every inserted entry starts a line, no indent
    gs.match_brace(g, gs.find_section(g, "landed_titles").open)   # still balanced


def test_the_campaign_entries_stay_byte_identical_apart_from_the_seams(tmp_path):
    save, _ = run_r14(tmp_path)
    before = titles_by_key(DEFAULT_META + SAVE)
    after = titles_by_key(save.gamestate)
    assert after["d_old"][1] == before["d_old"][1]
    assert after["k_old"][1] == before["k_old"][1].replace(b"{ 1 }", b"{ 1 5 }")


def test_r16_brings_the_holders_and_keeps_their_titles_held(tmp_path):
    save, res = migrate(tmp_path, SAVE, REF)
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
    save, res = migrate(tmp_path, body, ref)
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


def test_1c_a_baron_keeps_a_barony_1_20_put_in_a_new_county(tmp_path):
    """Step 1c (director 2026-10-26 04:45): a campaign barony whose 1.20 county is another one moves there, de
    jure and de facto, and its baron keeps it as a vassal of the 1.20 county's holder: the contract's liege, and
    the contract leaves the old liege's list and joins the new one's. Here the two moved baronies come from two
    old counts, so 1c-bis (which needs one old count) leaves the copied county with its copied holder."""
    save_body = gamestate(
        living=char(40, "\tlanded_data={\n\t\tdomain={ 0 }\n\t\tvassal_contracts={ 0 }\n\t}\n") + char(41)
        + char(42, "\tlanded_data={\n\t\tdomain={ 2 }\n\t\tvassal_contracts={ 1 }\n\t}\n") + char(43),
        titles=title(0, "c_a", "\tholder=40\n\tde_jure_vassals={ 1 }\n")
        + title(1, "b_x", "\tholder=41\n\tde_jure_liege=0\n\tde_facto_liege=0\n")
        + title(2, "c_b", "\tholder=42\n\tde_jure_vassals={ 3 }\n")
        + title(3, "b_z", "\tholder=43\n\tde_jure_liege=2\n\tde_facto_liege=2\n"),
        title_index=4,
        extra="provinces={\n1={\n}\n}\nvassal_contracts={\n\tactive={\n\t\t0={\n\t\t\tvassal=41\n\t\t\tliege=40\n"
              "\t\t}\n\t\t1={\n\t\t\tvassal=43\n\t\t\tliege=42\n\t\t}\n\t}\n}\n",
    )
    ref_body = gamestate(
        living=char(9, "\tlanded_data={\n\t\tdomain={ 4 }\n\t\tvassal_contracts={ }\n\t}\n"),
        titles=title(0, "c_a", "") + title(1, "b_x", "\tde_jure_liege=4\n") + title(2, "c_b", "")
        + title(3, "b_z", "\tde_jure_liege=4\n") + title(4, "c_new", "\tholder=9\n\tde_jure_vassals={ 1 3 }\n"),
        extra="provinces={\n1={\n}\n}\n",
    )
    save, res = migrate(tmp_path, save_body, ref_body)
    ex = res["R17"].extra
    assert ex["reparent_cases"] == {"baron only": 2} and ex["contracts_moved"] == 2 and ex["settled"] == []
    g = save.gamestate
    t = titles_by_key(g)
    c_new_id, c_new = t["c_new"]
    holder = int(re.search(rb"holder=(\d+)", c_new).group(1))
    assert f"de_jure_liege={c_new_id}".encode() in t["b_x"][1] and f"de_facto_liege={c_new_id}".encode() in t["b_x"][1]
    assert re.search(rb"de_jure_vassals=\{\s*\}", t["c_a"][1])                # b_x left its old county's list
    assert sorted(re.search(rb"de_jure_vassals=\{([^}]*)\}", c_new).group(1).split()) == [b"1", b"3"]
    c = gs.locate(g, "vassal_contracts/active")
    assert g[c.open:c.close].count(f"liege={holder}".encode()) == 2
    living = bodies(g, "living")
    assert re.search(rb"vassal_contracts=\{\s*\}", living[40]) and re.search(rb"vassal_contracts=\{\s*\}", living[42])
    assert re.search(rb"vassal_contracts=\{\s*0 1\s*\}", living[holder])


def _settle_fixture(tmp_path, player_house=None, capital=False, copied_baron=False, ruler_barony=False):
    """c_a (40, also holding b_y) and its baron 41 (b_x) on the campaign side; 1.20 puts b_x and b_y in the copied
    county c_new of the copied ruler 9, whose only title it is. ``copied_baron``: 1.20's history also has its own
    baron 10 on b_w in c_new, a vassal of 9 (contract 0)."""
    house = "\tdynasty_house=5\n" if player_house else ""
    save_body = gamestate(
        living=char(39, house) + char(40, "\tlanded_data={\n\t\tdomain={ 0 2 }\n\t\tvassal_contracts={ 0 }\n\t}\n")
        + char(41, house + "\tlanded_data={\n\t\tdomain={ 1 }\n\t}\n"),
        titles=title(0, "c_a", "\tholder=40\n\tde_jure_vassals={ 1 2 }\n")
        + title(1, "b_x", "\tholder=41\n\tde_jure_liege=0\n\tde_facto_liege=0\n")
        + title(2, "b_y", "\tholder=40\n\tde_jure_liege=0\n\tde_facto_liege=0\n"),
        title_index=3, houses='5={\n\tdynasty=7\n}\n' if player_house else "",
        extra="provinces={\n1={\n}\n}\nvassal_contracts={\n\tactive={\n\t\t0={\n\t\t\tvassal=41\n\t\t\tliege=40\n"
              "\t\t}\n\t}\n}\ncurrently_played_characters={ 39 }\n",
    )
    cap = "\tcapital_barony=yes\n" if capital else ""
    if copied_baron:
        living = (char(9, "\tlanded_data={\n\t\tdomain={ 3 }\n\t\tvassal_contracts={ 0 }\n\t\trealm_capital=3\n\t}\n")
                  + char(10, "\tlanded_data={\n\t\tdomain={ 4 }\n\t}\n"))
        more = title(4, "b_w", "\tholder=10\n\tde_jure_liege=3\n\tde_facto_liege=3\n")
        lst, contracts = "1 2 4", "vassal_contracts={\n\tdatabase={\n\t\t0={\n\t\t\tvassal=10\n\t\t\tliege=9\n\t\t}\n\t}\n}\n"
    elif ruler_barony:                                  # 9 also holds b_v, a barony of c_new
        living = char(9, "\tlanded_data={\n\t\tdomain={ 3 4 }\n\t\tvassal_contracts={ }\n\t\trealm_capital=3\n\t}\n")
        more, lst, contracts = title(4, "b_v", "\tholder=9\n\tde_jure_liege=3\n\tde_facto_liege=3\n"), "1 2 4", ""
    else:
        living = char(9, "\tlanded_data={\n\t\tdomain={ 3 }\n\t\tvassal_contracts={ }\n\t\trealm_capital=3\n\t}\n")
        more, lst, contracts = "", "1 2", ""
    ref_body = gamestate(
        living=living,
        titles=title(0, "c_a", "") + title(1, "b_x", "\tde_jure_liege=3\n" + cap)
        + title(2, "b_y", "\tde_jure_liege=3\n") + title(3, "c_new", f"\tholder=9\n\tde_jure_vassals={{ {lst} }}\n")
        + more,
        extra="provinces={\n1={\n}\n}\n" + contracts,
    )
    save, res = migrate(tmp_path, save_body, ref_body)
    g = save.gamestate
    return res["R17"].extra, g, titles_by_key(g), bodies(g, "living")


def test_1c_bis_the_old_count_takes_the_copied_county_and_its_ruler_goes_to_his_court(tmp_path):
    """Step 1c-bis (djdarcy's rule, transplant DWP 16:45): the copied county goes to the campaign. No baron is of
    the player's family, so the barony's old count (40) takes it; his baron (41) stays his vassal; the old count's
    own moved barony (b_y, the "mixed" case) simply comes with him. The copied ruler 9 loses his only title and
    goes to the new holder's court."""
    ex, g, t, living = _settle_fixture(tmp_path)
    assert ex["reparent_cases"] == {"settled (1c-bis)": 2} and ex["reparent_left"] == []
    assert {r["barony"]: (r["branch"], r["baron's fate"]) for r in ex["settled"]} == {
        "b_x": ("the old count takes it (a moved barony of his own came too)", "keeps the barony, vassal of 40"),
        "b_y": ("the old count takes it (a moved barony of his own came too)", "holds the county")}
    c_new_id, c_new = t["c_new"]
    assert b"holder=40" in c_new and b"de_facto_liege" not in c_new          # c_a has no de facto liege
    for b in ("b_x", "b_y"):
        assert f"de_jure_liege={c_new_id}".encode() in t[b][1] and f"de_facto_liege={c_new_id}".encode() in t[b][1]
    assert sorted(re.search(rb"de_jure_vassals=\{([^}]*)\}", c_new).group(1).split()) == [b"1", b"2"]
    assert ex["contracts_moved"] == 0 and re.search(rb"vassal_contracts=\{\s*0\s*\}", living[40])
    assert re.search(rf"domain=\{{[^}}]*\b{c_new_id}\b".encode(), living[40])
    (ruler,) = ex["settled_landless_rulers"]
    assert b"employer=40" in living[ruler] and re.search(rb"domain=\{\s*\}", living[ruler])
    assert b"realm_capital" not in living[ruler]


def test_1c_bis_a_baron_of_the_players_family_is_promoted(tmp_path):
    """A baron of the player's house is promoted to count of the copied county; the old count keeps his own."""
    ex, g, t, living = _settle_fixture(tmp_path, player_house=True)
    assert {r["branch"] for r in ex["settled"]} == {"family baron promoted (own house or dynasty)"}
    c_new_id, c_new = t["c_new"]
    assert b"holder=41" in c_new and b"holder=40" in t["c_a"][1]
    assert re.search(rf"domain=\{{[^}}]*\b{c_new_id}\b".encode(), living[41])
    (ruler,) = ex["settled_landless_rulers"]
    assert b"employer=41" in living[ruler]


def _attach_fixture(tmp_path):
    save_body, ref_body = _attach_bodies()
    save, res = migrate(tmp_path, save_body, ref_body)
    g = save.gamestate
    return res["R17"].extra, g, titles_by_key(g), bodies(g, "living")


def _attach_bodies():
    """The player (39) holds k_p; his count 40 holds c_old, whose baronies b_e1 and b_e2 are empty. An AI duke (50)
    holds d_ai over his count 51's c_ai, with empty b_e3 and b_e4. 1.20 carves three new counties from the empty
    baronies: c_newp (b_e1, b_e2) for ruler 9, independent in 1.20; c_newai (b_e3) for ruler 8, under d_ai in 1.20;
    c_newx (b_e4) for ruler 6, under the player's k_p in 1.20 though its land was the AI duke's."""
    ld = "\tlanded_data={{\n\t\tdomain={{ {} }}\n\t\tvassal_contracts={{ {} }}\n\t}}\n"
    save_body = gamestate(
        living=char(39, ld.format("0", "0")) + char(40, ld.format("1 2", "")) + char(50, ld.format("6", "1"))
        + char(51, ld.format("7 8", "")),
        titles=title(0, "k_p", "\tholder=39\n\tde_jure_vassals={ 1 }\n")
        + title(1, "c_old", "\tholder=40\n\tde_facto_liege=0\n\tde_jure_liege=0\n\tde_jure_vassals={ 2 3 4 }\n")
        + title(2, "b_held", "\tholder=40\n\tde_jure_liege=1\n\tde_facto_liege=1\n")
        + title(3, "b_e1", "\tde_jure_liege=1\n") + title(4, "b_e2", "\tde_jure_liege=1\n")
        + title(6, "d_ai", "\tholder=50\n\tde_jure_vassals={ 7 }\n")
        + title(7, "c_ai", "\tholder=51\n\tde_facto_liege=6\n\tde_jure_liege=6\n\tde_jure_vassals={ 8 9 10 }\n")
        + title(8, "b_ai", "\tholder=51\n\tde_jure_liege=7\n\tde_facto_liege=7\n")
        + title(9, "b_e3", "\tde_jure_liege=7\n") + title(10, "b_e4", "\tde_jure_liege=7\n"),
        title_index=11,
        extra="provinces={\n1={\n}\n}\nvassal_contracts={\n\tactive={\n\t\t0={\n\t\t\tvassal=40\n\t\t\tliege=39\n"
              "\t\t}\n\t\t1={\n\t\t\tvassal=51\n\t\t\tliege=50\n\t\t}\n\t}\n}\ncurrently_played_characters={ 39 }\n",
    )
    rl = "\tlanded_data={{\n\t\tdomain={{ {} }}\n\t\trealm_capital={}\n\t}}\n"
    ref_body = gamestate(
        living=char(9, rl.format("11", "3")) + char(8, rl.format("12", "9")) + char(6, rl.format("13", "10")),
        titles=title(0, "k_p", "") + title(1, "c_old", "") + title(2, "b_held", "")
        + title(3, "b_e1", "\tde_jure_liege=11\n") + title(4, "b_e2", "\tde_jure_liege=11\n")
        + title(6, "d_ai", "") + title(7, "c_ai", "") + title(8, "b_ai", "")
        + title(9, "b_e3", "\tde_jure_liege=12\n") + title(10, "b_e4", "\tde_jure_liege=13\n")
        + title(11, "c_newp", "\tholder=9\n\tde_jure_vassals={ 3 4 }\n")
        + title(12, "c_newai", "\tholder=8\n\tde_facto_liege=6\n\tde_jure_vassals={ 9 }\n")
        + title(13, "c_newx", "\tholder=6\n\tde_facto_liege=0\n\tde_jure_vassals={ 10 }\n"),
        extra="provinces={\n1={\n}\n}\n",
    )
    return save_body, ref_body


def _contract_to(g, vassal: int) -> tuple[bytes, int] | None:
    c = gs.locate(g, "vassal_contracts/active")
    m = re.search(rb"\n\t*(\d+)=\{\s*vassal=" + str(vassal).encode() + rb"\s*liege=(\d+)", g[c.open:c.close])
    return (m.group(1), int(m.group(2))) if m else None


def test_a_new_ruler_on_land_the_players_realm_held_joins_it(tmp_path):
    """djdarcy 2026-11-05: a county 1.20 carved from land the player's realm held puts its ruler in that realm, as
    the vassal of the campaign ruler who controlled the land; 1.20 had him independent, so a contract is written
    and the liege lists it."""
    ex, g, t, living = _attach_fixture(tmp_path)
    rows = {r["titles"][0]: r for r in ex["attached"]}
    assert rows["c_newp"]["liege"] == 39 and rows["c_newp"]["why"] == "capital on the player's land"
    assert b"de_facto_liege=0" in t["c_newp"][1]                  # k_p, the player's primary title
    ruler = int(re.search(rb"holder=(\d+)", t["c_newp"][1]).group(1))
    cid, liege = _contract_to(g, ruler)
    assert liege == 39 and re.search(rb"vassal_contracts=\{[^}]*\b" + cid + rb"\b", living[39])
    assert ex["contracts_created"] >= 1


def _with(body: bytes, section: bytes, add: str) -> bytes:
    return body.replace(section, section + add.encode(), 1)


def test_a_herder_stays_with_his_1_20_liege_where_1_20_never_pairs_him_with_the_campaign_one(tmp_path):
    """djdarcy 2026-11-05 (Kara Khoja's herders): 1.20 never puts a herder under a tribal ruler. The herder 8's
    1.20 liege 7 still rules d_keep in the output, so 8 stays 7's vassal (title and contract), not the tribal
    campaign duke 50's."""
    save_body, ref_body = _attach_bodies()
    save_body = save_body.replace(b"50={\n\tfirst_name=\"P50\"\n", b"50={\n\tfirst_name=\"P50\"\n\tgovernment=\"tribal_government\"\n", 1)
    ref_body = ref_body.replace(b"8={\n\tfirst_name=\"P8\"\n", b"8={\n\tfirst_name=\"P8\"\n\tgovernment=herder_government\n", 1)
    ref_body = _with(ref_body, b"living={\n", char(7, "\tgovernment=feudal_government\n\tlanded_data={\n\t\tdomain={ 6 14 }\n"
                                                         "\t\tvassal_contracts={ 0 }\n\t}\n"))
    ref_body = ref_body.replace(b"6={\n\tkey=d_ai\n}\n", b"6={\n\tkey=d_ai\n\tholder=7\n}\n", 1)
    ref_body = ref_body.replace(b"13={\n\tkey=c_newx\n", title(14, "d_keep", "\tholder=7\n").encode() + b"13={\n\tkey=c_newx\n", 1)
    ref_body += b"vassal_contracts={\n\tdatabase={\n\t\t0={\n\t\t\tvassal=8\n\t\t\tliege=7\n\t\t}\n\t}\n}\n"
    save, res = migrate(tmp_path, save_body, ref_body)
    g = save.gamestate
    rows = {r["titles"][0]: r for r in res["R17"].extra["attached"]}
    assert rows["c_newai"]["why"].startswith("stays with his 1.20 liege") and rows["c_newai"]["liege_title"] == "d_keep"
    t = titles_by_key(g)
    assert f"de_facto_liege={t['d_keep'][0]}".encode() in t["c_newai"][1]
    holder8 = int(re.search(rb"holder=(\d+)", t["c_newai"][1]).group(1))
    assert _contract_to(g, holder8)[1] == int(re.search(rb"holder=(\d+)", t["d_keep"][1]).group(1))


def test_a_seat_whose_1_20_liege_is_its_own_office_goes_to_the_ruler_of_its_land(tmp_path):
    """Constantinople (djdarcy: "that would be me"): 1.20's Patriarch holds both k_office and the seat; the campaign
    gave k_office to someone else (60). The office is his own, so the seat's land decides: c_old, the player's."""
    save_body, ref_body = _attach_bodies()
    save_body = _with(save_body, b"living={\n", char(60, "\tlanded_data={\n\t\tdomain={ 16 }\n\t}\n"))
    save_body = save_body.replace(b"6={\n\tkey=d_ai\n", title(16, "k_office", "\tholder=60\n").encode() + b"6={\n\tkey=d_ai\n", 1)
    ref_body = _with(ref_body, b"living={\n", char(5, "\tlanded_data={\n\t\tdomain={ 16 14 }\n\t}\n"))
    ref_body = ref_body.replace(b"13={\n\tkey=c_newx\n", title(16, "k_office", "\tholder=5\n").encode()
                                + title(14, "d_et_seat", "\tholder=5\n\tde_facto_liege=16\n\tcapital=1\n").encode()
                                + b"13={\n\tkey=c_newx\n", 1)
    save, res = migrate(tmp_path, save_body, ref_body)
    rows = {r["titles"][0]: r for r in res["R17"].extra["attached"]}
    assert rows["d_et_seat"]["liege"] == 39 and rows["d_et_seat"]["why"] == "landless: the ruler over its seat's land"


def test_a_noble_family_is_attached_only_under_an_administrative_liege(tmp_path):
    """A Byzantine noble family (administrative, landless) under the feudal player: its title would stick to its dead
    head (play10). It stays unattached; the game vacates it as it does with no administrative realm (s11)."""
    save_body, ref_body = _attach_bodies()
    ref_body = _with(ref_body, b"living={\n", char(5, "\tgovernment=administrative_government\n"
                                                      "\tlanded_data={\n\t\tdomain={ 14 }\n\t}\n"))
    ref_body = ref_body.replace(b"13={\n\tkey=c_newx\n", title(14, "d_nf_family", "\tholder=5\n\tde_facto_liege=0\n"
                                                                "\tcapital=1\n").encode() + b"13={\n\tkey=c_newx\n", 1)
    save, res = migrate(tmp_path, save_body, ref_body)
    ex = res["R17"].extra
    assert "d_nf_family" not in {r["titles"][0] for r in ex["attached"]}
    assert any(r["titles"] == ["d_nf_family"] and "noble families" in r["why"] for r in ex["attach_skipped"])


def test_noble_family_governments_are_read_from_the_game_files(tmp_path):
    """``noble_families = yes`` in common/governments; the 1.20.1.2 list when no game folder is given."""
    g = tmp_path / "common" / "governments"
    g.mkdir(parents=True)
    g.joinpath("x.txt").write_text("feudal_government = {\n\tnoble_families = no\n}\n"
                                   "admin_government = {\n\trules = { noble_families = yes }\n}\n"
                                   "# commented_government = {\n#\tnoble_families = yes\n# }\n")
    assert Transplant.noble_family_governments(tmp_path) == {b"admin_government"}
    assert b"administrative_government" in Transplant.noble_family_governments(None)


def test_a_holy_order_or_mercenary_government_is_never_attached(tmp_path):
    """The game's hard rule (common/governments, cannot_be_vassal_or_liege)."""
    g_dir = tmp_path / "game"
    (g_dir / "common" / "governments").mkdir(parents=True)
    (g_dir / "common" / "governments" / "x.txt").write_text(
        "mercenary_government = {\n\tflags = { cannot_be_vassal_or_liege }\n}\n", encoding="utf-8")
    save_body, ref_body = _attach_bodies()
    ref_body = ref_body.replace(b"9={\n\tfirst_name=\"P9\"\n", b"9={\n\tfirst_name=\"P9\"\n\tgovernment=mercenary_government\n", 1)
    save, res = migrate(tmp_path, save_body, ref_body, game_dir=g_dir)
    ex = res["R17"].extra
    assert "c_newp" not in {r["titles"][0] for r in ex["attached"]}
    assert any(r["titles"] == ["c_newp"] and "never a vassal" in r["why"] for r in ex["attach_skipped"])


def test_the_lock_step_pass_brings_every_copied_ruler_into_line_and_leaves_tributaries_alone():
    """djdarcy 2026-11-05 ("We do want to get to 100%"): for copied characters, the title liege and the contract
    agree after R17. 2: contract names 3, title names 1 -> the contract follows the title. 4: a contract to 1 and no
    title liege -> the title follows (1 rules k_a). 5: a title liege and no contract -> one is written. 6: a
    tributary contract with no title liege -> left alone. 7 is a campaign character -> left alone."""
    from ck3_save_migrator.rules.transplant_1_20 import _lock_step
    ld = "\tlanded_data={{\n\t\tdomain={{ {} }}\n\t\tvassal_contracts={{ {} }}\n\t}}\n"
    body = gamestate(
        living=char(1, ld.format("0", "")) + char(3, ld.format("9", "0")) + char(2, ld.format("1", ""))
        + char(4, ld.format("2", "")) + char(5, ld.format("3", "")) + char(6, ld.format("4", ""))
        + char(7, ld.format("5", "")),
        titles=title(0, "k_a", "\tholder=1\n") + title(9, "k_b", "\tholder=3\n")
        + title(1, "c_x", "\tholder=2\n\tde_facto_liege=0\n") + title(2, "c_y", "\tholder=4\n")
        + title(3, "c_z", "\tholder=5\n\tde_facto_liege=0\n") + title(4, "c_w", "\tholder=6\n")
        + title(5, "c_v", "\tholder=7\n"),
        extra="vassal_contracts={\n\tactive={\n\t\t0={\n\t\t\tvassal=2\n\t\t\tliege=3\n\t\t}\n\t\t1={\n\t\t\tvassal=4\n"
              "\t\t\tliege=1\n\t\t}\n\t\t2={\n\t\t\tvassal=6\n\t\t\tliege=1\n\t\t\tcontract_group=tributary_celestial\n"
              "\t\t}\n\t\t3={\n\t\t\tvassal=7\n\t\t\tliege=1\n\t\t}\n\t}\n}\ndate=987.10.27\n",
    )
    save = sf.parse_save(build_ck3(meta=DEFAULT_META, body=body))
    ctx = R.RuleContext()
    ctx.state["transplanted_characters"] = {"2", "4", "5", "6"}
    rows = _lock_step(save, ctx)
    assert rows == {"contract follows the title's liege": 1, "title follows the contract's liege": 1,
                    "contract written for a title liege": 1}
    g = save.gamestate
    t = titles_by_key(g)
    assert _contract_to(g, 2)[1] == 1 and b"de_facto_liege=0" in t["c_y"][1]
    assert _contract_to(g, 5)[1] == 1 and b"de_facto_liege" not in t["c_w"][1]
    assert b"de_facto_liege" not in t["c_v"][1]                       # the campaign's own: untouched
    living = bodies(g, "living")
    listed = set(re.search(rb"vassal_contracts=\{([^}]*)\}", living[1]).group(1).split())
    assert {b"0", _contract_to(g, 5)[0]} <= listed
    assert b"0" not in re.search(rb"vassal_contracts=\{([^}]*)\}", living[3]).group(1).split()


def test_a_written_contract_takes_a_slot_no_other_contract_uses(tmp_path):
    """A contract id is a slot index plus a generation in the top byte. "Largest id + 1" gave a new contract the
    slot of a campaign contract of another generation, and the game crashed (ck3+0x2ab8862, s15 and s17,
    2026-11-05: 29 shared slots). Here a contract of generation 15 has slot 5 and a campaign contract has slot 6."""
    from ck3_save_migrator import translate as T
    save_body, ref_body = _attach_bodies()
    high = (15 << 24) | 5
    save_body = save_body.replace(b"\t\t1={\n\t\t\tvassal=51\n", f"\t\t{high}={{\n\t\t\tvassal=901\n\t\t\tliege=902\n"
                                  f"\t\t}}\n\t\t6={{\n\t\t\tvassal=903\n\t\t\tliege=904\n\t\t}}\n\t\t1={{\n\t\t\tvassal=51\n"
                                  .encode(), 1)
    save, res = migrate(tmp_path, save_body, ref_body)
    g = save.gamestate
    ids = [int(e.key) for e in gs.iter_entries(g, *gs.locate(g, "vassal_contracts/active").body)]
    assert res["R17"].extra["contracts_created"] >= 1 and high in ids and 6 in ids
    slots = [T.index(i) for i in ids]
    assert len(slots) == len(set(slots)), sorted(slots)


def test_a_new_ruler_whose_1_20_liege_is_a_campaign_ai_title_becomes_its_holders_vassal(tmp_path):
    """Where 1.20 put him: under d_ai, which the campaign's AI duke 50 holds."""
    ex, g, t, living = _attach_fixture(tmp_path)
    rows = {r["titles"][0]: r for r in ex["attached"]}
    assert rows["c_newai"]["liege"] == 50 and rows["c_newai"]["why"] == "1.20 liege is a campaign title"
    assert b"de_facto_liege=6" in t["c_newai"][1]
    ruler = int(re.search(rb"holder=(\d+)", t["c_newai"][1]).group(1))
    cid, liege = _contract_to(g, ruler)
    assert liege == 50 and re.search(rb"vassal_contracts=\{[^}]*\b" + cid + rb"\b", living[50])


def test_a_new_ruler_under_the_players_title_on_land_he_never_held_stays_independent(tmp_path):
    """The player gains no one he never controlled: 1.20 puts c_newx under k_p, but its land was the AI duke's."""
    ex, g, t, living = _attach_fixture(tmp_path)
    assert [r["titles"] for r in ex["attach_independent"]] == [["c_newx"]]
    assert b"de_facto_liege" not in t["c_newx"][1]
    assert _contract_to(g, int(re.search(rb"holder=(\d+)", t["c_newx"][1]).group(1))) is None


def test_a_landless_seat_follows_its_1_20_liege_into_the_players_realm(tmp_path):
    """djdarcy 14:03: a landless 1.20 title (an ecclesiastical seat) is never independent in 1.20, so it takes
    1.20's own liege at its campaign holder, even inside the player's realm: the land test has no land to read.
    d_et_seat sits under k_p in 1.20 with its seat at c_old; the player holds k_p."""
    save_body, ref_body = _attach_bodies()
    ref_body = ref_body.replace(b"living={\n", b"living={\n" + char(5, "\tlanded_data={\n\t\tdomain={ 14 }\n\t}\n")
                                .encode(), 1)
    ref_body = ref_body.replace(
        b"13={\n\tkey=c_newx\n", title(14, "d_et_seat", "\tholder=5\n\tde_facto_liege=0\n\tcapital=1\n").encode()
        + b"13={\n\tkey=c_newx\n", 1)
    # a holy order, landless and independent in 1.20, stays independent (s14: 12 orders were attached by mistake)
    ref_body = ref_body.replace(b"living={\n", b"living={\n" + char(4, "\tlanded_data={\n\t\tdomain={ 15 }\n\t}\n")
                                .encode(), 1).replace(
        b"13={\n\tkey=c_newx\n", title(15, "d_order", "\tholder=4\n\tcapital=1\n").encode() + b"13={\n\tkey=c_newx\n", 1)
    # the player's first-listed title is a runtime x_x_ title, as on the founding save (s14: York and Split were
    # skipped because the rank was read from it): his rank is his highest title's
    save_body = save_body.replace(b"domain={ 0 }", b"domain={ 11 0 }", 1).replace(
        b"\tindex=11", b"\tindex=12", 1).replace(b"6={\n\tkey=d_ai\n", title(11, "x_x_9", "\tholder=39\n").encode()
                                                  + b"6={\n\tkey=d_ai\n", 1)
    save, res = migrate(tmp_path, save_body, ref_body)
    g = save.gamestate
    rows = {r["titles"][0]: r for r in res["R17"].extra["attached"]}
    assert rows["d_et_seat"]["liege"] == 39 and rows["d_et_seat"]["why"] == "landless: 1.20's liege, at its campaign holder"
    assert "d_order" not in rows
    t = titles_by_key(g)
    assert b"de_facto_liege=11" in t["d_et_seat"][1]            # the player's primary, the x_x_ title
    cid, liege = _contract_to(g, int(re.search(rb"holder=(\d+)", t["d_et_seat"][1]).group(1)))
    assert liege == 39
    assert b"de_facto_liege" not in t["d_order"][1]
    assert _contract_to(g, int(re.search(rb"holder=(\d+)", t["d_order"][1]).group(1))) is None


def test_1c_bis_a_promoted_baron_gets_the_county_as_his_primary_title(tmp_path):
    """The first domain entry is the primary title. A promoted baron's county must come before his barony: with the
    barony first, 1.20 making him independent sets the county's liege to the county itself, and its "which kingdom"
    routine loops forever (the 987.11.8 freeze of 2026-10-27, c_kuzeytorg)."""
    ex, g, t, living = _settle_fixture(tmp_path, player_house=True)
    c_new_id = t["c_new"][0]
    dom = re.search(rb"domain=\{([^}]*)\}", living[41]).group(1).split()
    assert dom[0] == str(c_new_id).encode() and b"1" in dom          # the county first, the barony b_x kept


def test_a_domain_starting_with_a_runtime_title_is_left_alone():
    from ck3_save_migrator.transplant import _primary_first
    keys = {1: "b_a", 2: "c_a", 7: "x_x_762", 8: "e_big"}.get
    promoted = b"5={\n\tlanded_data={\n\t\tdomain={ 1 2 }\n\t}\n}"
    assert b"domain={ 2 1 }" in _primary_first(promoted, lambda i: keys(i, ""))
    ruler = b"5={\n\tlanded_data={\n\t\tdomain={ 7 8 }\n\t}\n}"                # the campaign's own x_ primary
    assert _primary_first(ruler, lambda i: keys(i, "")) == ruler
    already = b"5={\n\tlanded_data={\n\t\tdomain={ 2 1 }\n\t}\n}"
    assert _primary_first(already, lambda i: keys(i, "")) == already


def test_1c_bis_a_copied_baron_in_the_county_becomes_the_new_counts_vassal(tmp_path):
    """Ruling Q2 (director 17:3x): a baron 1.20's history put in the county stays a baron, now a vassal of the new
    (campaign) count: his contract names the new count, and it leaves the displaced ruler's list for his."""
    ex, g, t, living = _settle_fixture(tmp_path, copied_baron=True)
    assert b"holder=40" in t["c_new"][1]
    b_w = t["b_w"][1]
    baron = int(re.search(rb"holder=(\d+)", b_w).group(1))
    c = gs.locate(g, "vassal_contracts/active")
    body = g[c.open:c.close]
    m = re.search(rb"\n\t*(\d+)=\{\s*vassal=" + str(baron).encode() + rb"\s*liege=(\d+)", body)
    assert m and int(m.group(2)) == 40, body
    cid = m.group(1)
    assert re.search(rb"vassal_contracts=\{[^}]*\b" + cid + rb"\b", living[40])
    (ruler,) = ex["settled_landless_rulers"]                 # 9, whose only title c_new was
    assert not re.search(rb"vassal_contracts=\{[^}]*\b" + cid + rb"\b", living[ruler])


def test_1c_bis_a_barony_the_displaced_ruler_holds_in_the_county_stays_his_and_is_named(tmp_path):
    """Director 2026-10-26 18:0x: the displaced ruler's own other barony in the county is left with him (the game
    keeps it with him on load), and the report names it; he keeps it, so he is not landless."""
    ex, g, t, living = _settle_fixture(tmp_path, ruler_barony=True)
    rows = {r["barony"]: r for r in ex["settled"]}
    assert rows["b_v"]["baron's fate"] == "held by the displaced ruler, left with him"
    ruler = rows["b_v"]["old holder"]
    assert f"holder={ruler}".encode() in t["b_v"][1] and b"holder=40" in t["c_new"][1]
    assert ex["settled_landless_rulers"] == [] and b"employer=40" not in living[ruler]
    assert re.search(rf"realm_capital={t['b_v'][0]}".encode(), living[ruler])     # his capital moves to b_v


def test_1c_bis_a_capital_baron_who_is_not_the_new_count_goes_landless_to_his_court(tmp_path):
    """Ruling Q1 (director 17:3x): the county's holder always holds its capital barony and no built barony is free,
    so a capital baron who is not the new count gives his barony to him, loses his contract, and joins his court."""
    ex, g, t, living = _settle_fixture(tmp_path, capital=True)
    rows = {r["barony"]: r for r in ex["settled"]}
    assert "landless" in rows["b_x"]["baron's fate"]
    assert b"holder=40" in t["b_x"][1]
    assert b"employer=40" in living[41] and re.search(rb"domain=\{\s*\}", living[41])
    c = gs.locate(g, "vassal_contracts/active")
    assert b"vassal=41" not in g[c.open:c.close]
    assert re.search(rb"vassal_contracts=\{\s*\}", living[40])
    assert re.search(rb"domain=\{[^}]*\b1\b", living[40])


def test_1c_a_capital_barony_is_named_not_moved(tmp_path):
    """Ruling A: the game gives a county's capital barony to the county's holder, so a lone baron whose barony is
    the capital of its 1.20 county cannot keep it; the case is named (re-save of e2e_1c4: 11 of 18 lost). The
    1.20 county here is a CAMPAIGN county (held by 42), so 1c-bis does not apply: the game's rule stands."""
    save_body = gamestate(
        living=char(40) + char(41) + char(42),
        titles=title(0, "c_a", "\tholder=40\n\tde_jure_vassals={ 1 }\n")
        + title(1, "b_x", "\tholder=41\n\tde_jure_liege=0\n\tde_facto_liege=0\n")
        + title(2, "c_new", "\tholder=42\n"),
        title_index=3, extra="provinces={\n1={\n}\n}\n")
    ref_body = gamestate(
        living=char(9),
        titles=title(0, "c_a", "") + title(1, "b_x", "\tde_jure_liege=2\n\tcapital_barony=yes\n")
        + title(2, "c_new", "\tholder=9\n\tde_jure_vassals={ 1 }\n"),
        extra="provinces={\n1={\n}\n}\n")
    save, res = migrate(tmp_path, save_body, ref_body)
    ex = res["R17"].extra
    assert ex["reparent_cases"] == {"capital": 1}
    assert ex["reparent_left"][0]["barony"] == "b_x" and "capital" in ex["reparent_left"][0]["reason"]
    assert b"de_jure_liege=0" in titles_by_key(save.gamestate)["b_x"][1]


def test_1c_a_copied_barony_on_an_empty_campaign_province_gets_the_reference_holding(tmp_path):
    """Ruling B: a copied barony on a province the campaign kept with no holding brings the reference's province
    entry (b_luoshan, province 8985: city baron stripped on load). A campaign barony the campaign never built stays
    unbuilt and is counted."""
    game = tmp_path / "game"
    (game / "common" / "landed_titles").mkdir(parents=True)
    (game / "common" / "landed_titles" / "00_t.txt").write_text(
        "c_new = { b_new = { province = 1 } }\nc_old = { b_old = { province = 2 } }\n", encoding="utf-8")
    save_body = gamestate(
        living=char(40),
        titles=title(0, "c_old", "\tholder=40\n\tde_jure_vassals={ 1 }\n") + title(1, "b_old", "\tde_jure_liege=0\n"),
        title_index=2, extra="provinces={\n\t1={\n\t\tholding={\n\t\t\tincome=0\n\t\t}\n\t}\n"
                             "\t2={\n\t\tholding={\n\t\t\tincome=0\n\t\t}\n\t}\n}\n")
    ref_body = gamestate(
        living=char(9),
        titles=title(0, "c_old", "") + title(1, "b_old", "\tde_jure_liege=0\n")
        + title(2, "c_new", "\tholder=9\n\tde_jure_vassals={ 3 }\n") + title(3, "b_new", "\tholder=9\n\tde_jure_liege=2\n"),
        extra="provinces={\n1={\n\tholding={\n\t\ttype=city_holding\n\t}\n}\n"
              "2={\n\tholding={\n\t\ttype=castle_holding\n\t}\n}\n}\n")
    save, res = migrate(tmp_path, save_body, ref_body, game_dir=game)
    assert res["R14"].extra["provinces_given_a_holding"] == 1
    assert res["R14"].extra["unbuilt_in_the_campaign_built_in_a_fresh_1_20_game"] == 1
    assert res["R17"].extra["provinces_filled"] == 1
    prov = bodies(save.gamestate, "provinces")
    assert b"city_holding" in prov[1] and b"castle_holding" not in prov[2]


def test_1c_a_copied_barony_in_a_campaign_county_whose_holder_holds_land_elsewhere_is_named(tmp_path):
    """The mirror of the mixed case: a copied barony inside a campaign county, held by a copied ruler who holds land
    outside that county, goes with the county to its campaign holder on load (4 on the re-save of e2e_1c5)."""
    save_body = gamestate(living=char(40), titles=title(0, "c_a", "\tholder=40\n"), title_index=1,
                          extra="provinces={\n1={\n}\n}\n")
    ref_body = gamestate(
        living=char(9),
        titles=title(0, "c_a", "\tde_jure_vassals={ 1 }\n") + title(1, "b_n", "\tholder=9\n\tde_jure_liege=0\n")
        + title(2, "c_far", "\tholder=9\n"),
        extra="provinces={\n1={\n}\n}\n")
    save, res = migrate(tmp_path, save_body, ref_body)
    ex = res["R17"].extra
    assert ex["reparent_cases"] == {"goes with its county": 1}
    (row,) = ex["reparent_left"]
    assert row["barony"] == "b_n" and row["goes to"] == 40 and "campaign holder 40" in row["reason"]


def test_s3_a_campaign_title_whose_old_parent_died_joins_its_1_20_parent(tmp_path):
    """S3 (director 2026-10-26 00:45): a campaign title left with no de jure parent (R15 removed its 1.8.1 one)
    gets the parent 1.20's map gives it, from the reference's tree: here a copied kingdom (d_a, listed by the
    copied k_new) and a campaign kingdom (d_b, appended to k_camp's list). A title the save gives a parent is
    never touched."""
    save_body = gamestate(
        living=char(40),
        titles=title(0, "d_a", "\tholder=40\n") + title(1, "d_b", "\tholder=40\n")
        + title(2, "k_camp", "\tde_jure_vassals={ 3 }\n") + title(3, "d_c", "\tde_jure_liege=2\n"),
        title_index=4, extra="provinces={\n1={\n}\n}\n")
    ref_body = gamestate(
        living=char(9),
        titles=title(0, "d_a", "\tde_jure_liege=4\n") + title(1, "d_b", "\tde_jure_liege=2\n")
        + title(2, "k_camp", "\tde_jure_vassals={ 1 3 }\n") + title(3, "d_c", "\tde_jure_liege=4\n")
        + title(4, "k_new", "\tholder=9\n\tde_jure_vassals={ 0 3 }\n"),
        extra="provinces={\n1={\n}\n}\n")
    save, res = migrate(tmp_path, save_body, ref_body)
    ex = res["R17"].extra
    assert sorted(ex["orphans_reparented"]) == ["d_a -> k_new", "d_b -> k_camp"]
    t = titles_by_key(save.gamestate)
    k_new_id, k_new = t["k_new"]
    assert f"de_jure_liege={k_new_id}".encode() in t["d_a"][1] and b"de_jure_liege=2" in t["d_b"][1]
    assert b"de_jure_liege=2" in t["d_c"][1]                    # had a parent: untouched (1.20 differs, G10)
    assert b" 0 " in re.search(rb"de_jure_vassals=\{[^}]*\}", k_new).group(0)
    assert sorted(re.search(rb"de_jure_vassals=\{([^}]*)\}", t["k_camp"][1]).group(1).split()) == [b"1", b"3"]


def _lease_run(tmp_path, expansion: bool):
    save_body = gamestate(
        living=char(40),
        titles=title(0, "b_free", "\tholder=40\n") + title(1, "b_taken", "\tholder=40\n\tlessee=2\n")
        + title(2, "d_old_order", ""), title_index=3, extra="provinces={\n1={\n}\n}\n")
    ref_body = gamestate(
        living=char(9),
        titles=title(0, "b_free", "") + title(1, "b_taken", "") + title(2, "d_old_order", "")
        + title(3, "d_order", "\tholder=9\n\tholy_order=0\n"),
        extra="provinces={\n1={\n}\n}\nholy_orders={\n\tholy_orders={\n\t\t0={\n\t\t\ttitle=3\n"
              "\t\t\ttitles={ 0 1 }\n\t\t\tfounder=9\n\t\t}\n\t}\n}\n")
    save, res = migrate(tmp_path, save_body, ref_body, expansion_orders=expansion)
    return save, res["R17"].extra, DEFAULT_META + save_body


def test_s10_a_lease_is_written_only_on_a_barony_the_order_leases_and_that_is_not_already_leased(tmp_path):
    """S10 (director 2026-10-26 00:45): an expansion order's lease goes on a campaign barony the reference's order
    leases and that is not already leased; a barony with a lease of its own keeps it; the report lists every lease."""
    save, ex, before = _lease_run(tmp_path, expansion=True)
    t = titles_by_key(save.gamestate)
    order_id = t["d_order"][0]
    assert f"lessee={order_id}".encode() in t["b_free"][1]
    assert b"lessee=2" in t["b_taken"][1] and f"lessee={order_id}".encode() not in t["b_taken"][1]
    assert ex["expansion_content_added"] == {"holy_orders": ["d_order"], "leases": ["b_free -> d_order"]}


def test_s10_no_expansion_orders_writes_no_lease_and_leaves_the_campaign_titles_alone(tmp_path):
    """S10: --no-expansion-orders: the order is not added, no lease edit, the campaign's titles byte-identical."""
    save, ex, before = _lease_run(tmp_path, expansion=False)
    t, b = titles_by_key(save.gamestate), titles_by_key(before)
    assert "d_order" not in t and ex["expansion_content_added"] == {"holy_orders": [], "leases": []}
    for k in ("b_free", "b_taken", "d_old_order"):
        assert t[k][1] == b[k][1]


def test_the_transplant_on_its_own_output_writes_nothing(tmp_path):
    """S11 (director 2026-10-26 00:45): every rule is idempotent on its own output; R14 and R16 run again on what
    R17 wrote plan nothing, and R17 edits 0."""
    save, _ = run_r14(tmp_path)
    _, res2 = migrate(tmp_path, save.gamestate[len(DEFAULT_META):], REF)
    assert res2["R14"].extra["titles_planned"] == 0 and res2["R14"].extra["provinces_planned"] == 0
    assert res2["R17"].edited == 0


def test_r15_steps_aside_on_a_save_already_at_the_target_version(tmp_path):
    """S11 (measured 2026-10-26): R15's mapping comes from the two maps' files, which still differ on a migrated
    save; re-run on the founding save's output it swapped two renamed baronies back and removed 8 moved ones. A
    save that already says it is at the target version is on the target map: R15 skips, and nothing changes."""
    meta = DEFAULT_META.replace(b'version="1.8.1"', b'version="1.20.1.2"')
    body = SAVE.replace(b'version="1.8.1"', b'version="1.20.1.2"')
    save = sf.parse_save(build_ck3(meta=meta, body=body))
    before = save.gamestate
    ctx = R.RuleContext(game_dir=tmp_path, old_game_dir=tmp_path)          # folders R15 must not even read
    res = {r.id: r for r in R.run_rules(save, R.select("R15"), ctx)}            # R15 brings R17 along
    assert "already at 1.20.1.2" in res["R15"].extra["skipped"] and res["R15"].edited == 0
    assert res["R17"].edited == 0 and save.gamestate == before


def test_r16_plans_only_the_situation_types_the_save_lacks(tmp_path):
    """S11 (measured 2026-10-26): R16 planned every reference situation on every run, so a second migration inserted
    them again; it now plans only the types the save does not have (a 1.8.1 save has none, so all of them)."""
    sit = "situation_manager={\n\tdatabase={\n%s\t}\n}\n"
    one = "\t\t%d={\n\t\t\ttype=%s\n\t\t}\n"
    save, res = migrate(tmp_path, SAVE + (sit % (one % (0, "dynastic_cycle"))).encode(),
                        REF + (sit % (one % (0, "dynastic_cycle") + one % (1, "the_great_steppe"))).encode())
    assert res["R17"].extra["planned"]["R16 situation"] == 1
    g = save.gamestate
    b = gs.locate(g, "situation_manager/database")
    types = re.findall(rb"type=(\w+)", g[b.open:b.close])
    assert sorted(types) == [b"dynastic_cycle", b"the_great_steppe"]


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
