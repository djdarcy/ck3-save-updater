"""A 1.21 save or reference read by the 1.20 machinery (S10, 2026-11-18).

1.21 writes a title's key on its type line (`type=title_type_x\tkey=c_y`). The 1.20 patterns read 19 of a 1.21
reference's 20,499 keys, so the transplant copied a second world (12,086 keys held twice) and lint's own duplicate-key
check, which used the same pattern, saw none of it. Each case below is one of those lessons.
"""
from ck3_save_migrator import lint as L
from ck3_save_migrator import transplant as TP
from ck3_save_migrator.rules import transplant_1_20 as R


def titles(rows: str) -> bytes:
    return f"landed_titles={{\n\tlanded_titles={{\n{rows}\t}}\n}}\n".encode()


def t120(i, key, holder=None):
    return f"{i}={{\n\tkey={key}\n" + (f"\tholder={holder}\n" if holder else "") + "}\n"


def t121(i, key, typ="title_type_default_static", holder=None):
    return f"{i}={{\n\ttype={typ}\tkey={key}\n" + (f"\tholder={holder}\n" if holder else "") + "}\n"


def findings(g: bytes) -> dict:
    rep = L.LintReport()
    L.check_titles(g, rep)
    return {f.check: f for f in rep.findings}


def test_a_reference_whose_titles_join_none_of_the_saves_is_refused():
    save_keys = {b"d_a", b"d_b", b"c_c", b"c_d"}
    # what the chain saw: keys unread ("?"), so nothing joined and R14 would have taken every title as new
    assert "do not join" in R.unread_reference(save_keys, {1: "?", 2: "?", 3: "?", 4: "?"})
    # a reference made at the campaign's date shares most keys: no refusal
    assert R.unread_reference(save_keys, {1: "d_a", 2: "d_b", 3: "c_c", 4: "c_new"}) is None
    # readable keys that are simply foreign (another campaign's date or another game) are refused too
    assert "do not join" in R.unread_reference(save_keys, {1: "d_x", 2: "d_y", 3: "c_z", 4: "c_w"})
    # a partial read is refused even when what was read joins: the unread rest would be copied as new
    many = {b"k%d" % i for i in range(100)}
    part = {i: (f"k{i}" if i < 60 else "?") for i in range(100)}
    assert "do not join" in R.unread_reference(many, part)


def test_lint_sees_a_title_key_held_twice_across_the_two_layouts():
    # the chain's shape: a campaign row in 1.20 layout and a copied reference row in 1.21 layout, one key
    f = findings(titles(t120(1, "k_papal_state") + t121(2, "k_papal_state")))
    assert f["title keys are unique"].count == 1


def test_lint_does_not_ask_a_county_record_of_a_family_title():
    # a fresh 1.21 game holds 8 noble family titles (c_nf_), none with a county_manager record; land still needs one
    g = titles(t121(1, "c_nf_doukas", "title_type_noble_family", holder=5) + t120(2, "c_land", holder=6)) + \
        b"county_manager={\n\tcounties={\n\t}\n}\n"
    f = findings(g)
    assert f["held counties have a county record"].examples == ["c_land"]


def test_a_barony_with_a_nested_block_before_its_province_is_read(tmp_path):
    # 14 baronies of 1.21's title files carry a block before `province =`; the old regex missed them (F7 audit)
    from ck3_save_migrator import mapdata as M
    d = tmp_path / "common" / "landed_titles"
    d.mkdir(parents=True)
    (d / "t.txt").write_text("c_x = {\n\tb_asmat = {\n\t\tcolor = { 1 2 3 }\n\t\tprovince = 77\n\t}\n"
                             "\tb_plain = {\n\t\tprovince = 78\n\t}\n}\n", encoding="utf-8")
    M.barony_provinces.cache_clear()
    assert M.barony_provinces(tmp_path) == {"b_asmat": 77, "b_plain": 78}


def test_1_21_runtime_keys_split_into_family_and_number():
    assert TP._RUNTIME_KEY.match(b"x_d_mc_0").groups() == (b"x_d_mc_", b"0")
    assert TP._RUNTIME_KEY.match(b"x_c_nomad_553").groups() == (b"x_c_nomad_", b"553")
    assert TP._RUNTIME_KEY.match(b"x_mc_6").groups() == (b"x_mc_", b"6")
