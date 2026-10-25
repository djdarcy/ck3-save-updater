"""Tests for ck3_save_migrator.gamestate -- locating, iterating and editing raw gamestate bytes.

Synthetic gamestates only (tests/fixtures/make_ck3.py), except the reference-count
checks at the bottom, which read the gitignored extracted gamestates when present.
"""

from __future__ import annotations

import types
from pathlib import Path

import pytest

from ck3_save_migrator import gamestate as gs
from ck3_save_migrator import savefile as sf
from tests.fixtures.make_ck3 import DEFAULT_META, NESTED_BODY, build_ck3

ROOT = Path(__file__).resolve().parents[1]
EXTRACTED = ROOT / "private" / "data" / "extracted"
REF_GS = EXTRACTED / "ref_1_20_persia_867" / "gamestate"
OLD_GS = EXTRACTED / "987_10_27_husband_died" / "gamestate"

DATA = DEFAULT_META + NESTED_BODY


def expected_after(before: bytes, edits: list[tuple[int, int, bytes]]) -> bytes:
    """``before`` with exactly these (start, end, replacement) edits and nothing else.

    Stricter than a difflib check (difflib may align a deleted "\\n\\tX" one byte
    off from the "\\tX\\n" that was removed); every other byte must match exactly.
    """
    out, pos = [], 0
    for s, e, r in sorted(edits):
        out += [before[pos:s], r]
        pos = e
    return b"".join(out + [before[pos:]])


def line_of(data: bytes, needle: bytes) -> tuple[int, int, bytes]:
    """The whole line containing ``needle`` (newline included), as a deletion edit."""
    i = data.index(needle)
    s = data.rfind(b"\n", 0, i) + 1
    return s, data.index(b"\n", i) + 1, b""


def entry(data: bytes, path: str, key: bytes | None, index: int = 0) -> gs.Block:
    blocks = [b for b in gs.iter_entries(data, *gs.locate(data, path).body) if b.key == key]
    return blocks[index]


# --------------------------------------------------------------------------- locating
class TestLocate:
    def test_find_section(self):
        b = gs.find_section(DATA, "living")
        assert DATA[b.start:b.open + 1] == b"living={"
        assert DATA[b.close:b.close + 2] == b"}\n"

    def test_meta_data_is_a_section(self):
        b = gs.find_section(DATA, "meta_data")
        assert b.end + 1 == len(DEFAULT_META)

    def test_repeated_top_level_key(self):
        found = list(gs.find_sections(DATA, "triggered_event"))
        assert [DATA[b.open:b.end] for b in found] == [b"{ id=1 }", b"{ id=2 }"]

    def test_missing_section(self):
        with pytest.raises(gs.GamestateError, match="not found"):
            gs.find_section(DATA, "rites")

    def test_indented_key_is_not_top_level(self):
        # 'faiths={' exists only indented inside religion; it is not a top-level section
        with pytest.raises(gs.GamestateError, match="not found"):
            gs.find_section(DATA, "faiths")

    def test_inner_child_skips_decoy_id_list(self):
        faiths = gs.locate(DATA, "religion/faiths")
        body = DATA[faiths.open:faiths.end]
        assert b'tag="catholic"' in body and b"{ 0 1 }" not in body

    def test_inner_landed_titles_not_dynamic_templates(self):
        lt = gs.locate(DATA, "landed_titles/landed_titles")
        assert b"k_papal_state" in DATA[lt.open:lt.end]
        assert b"x_x_1" not in DATA[lt.open:lt.end]

    def test_missing_child(self):
        with pytest.raises(gs.GamestateError, match="depth 0"):
            gs.locate(DATA, "religion/rites")

    def test_match_brace_skips_strings(self):
        start = DATA.index(b"1={\n\tfirst_name=\"Beidh") + 2      # "Beidh {not a block" has a stray "{"
        close = gs.match_brace(DATA, start)
        assert DATA[close - 3:close + 3] == b"\t}\n}\n\n"
        assert b"2={" not in DATA[start:close]


# --------------------------------------------------------------------------- iterating
class TestIterate:
    def test_entries_are_lazy(self):
        assert isinstance(gs.iter_entries(DATA, *gs.find_section(DATA, "living").body), types.GeneratorType)

    def test_living_entries(self):
        keys = [b.key for b in gs.iter_entries(DATA, *gs.find_section(DATA, "living").body)]
        assert keys == [b"1", b"2"]

    def test_entry_ends_despite_quoted_braces(self):
        e2 = entry(DATA, "living", b"2")
        assert DATA[e2.open:e2.end].endswith(b"9999.1.1\n\t}\n}")

    def test_anonymous_list_layout(self):
        items = list(gs.iter_entries(DATA, *gs.locate(DATA, "opinions/active_opinions").body))
        assert [b.key for b in items] == [None, None]
        assert b"owner=1" in DATA[items[0].open:items[0].end]
        assert b"owner=2" in DATA[items[1].open:items[1].end]

    def test_children_spans(self):
        e2 = entry(DATA, "living", b"2")
        kids = {c.key: c for c in gs.iter_children(DATA, *e2.body)}
        assert set(kids) == {b"first_name", b"female", b"faith", b"color", b"alive_data"}
        assert DATA[kids[b"color"].value_start:kids[b"color"].value_end] == b"rgb { 1 2 3 }"
        assert DATA[kids[b"first_name"].value_start:kids[b"first_name"].value_end] == \
            b'"Simin \\"the } quoted\\""'

    def test_two_keys_on_one_line(self):
        ad = gs.find_keys(DATA, entry(DATA, "living", b"2"), "alive_data")[0].block
        kids = [c.key for c in gs.iter_children(DATA, *ad.body)]
        assert kids == [b"modifier", b"expiration_date"]

    def test_empty_key(self):
        e1 = entry(DATA, "living", b"1")
        ld = gs.find_keys(DATA, e1, "landed_data")[0].block
        dc = gs.find_keys(DATA, ld, "decision_cooldowns")[0].block
        (c,) = gs.iter_children(DATA, *dc.body)
        assert c.key == b"" and DATA[c.start:c.end] == b"=-5000.1.1"

    def test_bare_list_values(self):
        skill = gs.find_keys(DATA, entry(DATA, "living", b"1"), "skill")[0].block
        vals = [DATA[c.start:c.end] for c in gs.iter_children(DATA, *skill.body)]
        assert vals == [b"6", b"4", b"8", b"7", b"7", b"5"]

    def test_unbalanced(self):
        with pytest.raises(gs.GamestateError):
            list(gs.iter_entries(b"a={ b={ }", 0, 9))
        with pytest.raises(gs.GamestateError):
            list(gs.iter_entries(b"a={ } }", 0, 7))


# --------------------------------------------------------------------------- editing (A2)
class TestEdits:
    def test_delete_block_value_whole_lines(self):
        op = entry(DATA, "opinions/active_opinions", None, 0)
        to = gs.find_keys(DATA, op, "temporary_opinion")[0].block
        p = gs.EditPass()
        assert p.delete_key(DATA, to, "converging", "converging") == 1
        after = p.apply(DATA)
        cv = DATA.index(b"\t\t\t\tconverging")
        cv_end = DATA.index(b"\t\t\t\t}\n", cv) + len(b"\t\t\t\t}\n")
        assert after == expected_after(DATA, [(cv, cv_end, b"")])
        assert b"modifier=\"impressed_opinion\"\n\t\t\t\tvalue=5" in after

    def test_delete_scalar_across_entries_in_one_pass(self):
        lt = gs.locate(DATA, "landed_titles/landed_titles")
        p = gs.EditPass()
        for t in gs.iter_entries(DATA, *lt.body):
            p.count("title-names").matched += 1
            for k in ("name", "adj", "article", "pre"):
                p.delete_key(DATA, t, k, "title-names")
        after = p.apply(DATA)
        assert p.counts["title-names"].matched == 2 and p.counts["title-names"].edited == 4
        for gone in (b'name="Papacy"', b'adj="Papal"', b'article="the "', b'name="Ireland"'):
            assert gone not in after
        assert b'key="k_papal_state"\n\tdate=976.3.4' in after
        lines = [line_of(DATA, x) for x in (b'name="Papacy"', b'adj="Papal"', b'article="the "', b'name="Ireland"')]
        assert after == expected_after(DATA, lines)

    def test_delete_first_of_two_keys_on_a_line(self):
        ad = gs.find_keys(DATA, entry(DATA, "living", b"2"), "alive_data")[0].block
        p = gs.EditPass()
        p.delete_key(DATA, ad, "modifier", "r")
        i = DATA.index(b"modifier=world_modifier")
        assert p.apply(DATA) == expected_after(DATA, [(i, i + len(b"modifier=world_modifier\t\t\t"), b"")])

    def test_delete_second_of_two_keys_on_a_line(self):
        ad = gs.find_keys(DATA, entry(DATA, "living", b"2"), "alive_data")[0].block
        p = gs.EditPass()
        p.delete_key(DATA, ad, "expiration_date", "r")
        i = DATA.index(b"\t\t\texpiration_date=9999.1.1")
        assert p.apply(DATA) == expected_after(DATA, [(i, i + len(b"\t\t\texpiration_date=9999.1.1"), b"")])

    def test_delete_empty_key(self):
        e1 = entry(DATA, "living", b"1")
        dc = gs.find_keys(DATA, gs.find_keys(DATA, e1, "landed_data")[0].block, "decision_cooldowns")[0].block
        p = gs.EditPass()
        assert p.delete_key(DATA, dc, b"", "empty-key") == 1
        after = p.apply(DATA)
        assert b"decision_cooldowns={\n\t\t}" in after
        assert after == expected_after(DATA, [line_of(DATA, b"=-5000.1.1")])

    def test_delete_does_not_touch_nested_same_name(self):
        # religion body has a depth-0 'faiths' (database) and a nested 'faiths' id list
        rel = gs.find_section(DATA, "religion")
        p = gs.EditPass()
        assert p.delete_key(DATA, rel, "faiths", "r") == 1
        after = p.apply(DATA)
        assert b"faiths={ 0 1 }" in after and b"catholic" not in after

    def test_delete_block_entry(self):
        e1 = entry(DATA, "living", b"1")
        p = gs.EditPass()
        p.delete_block(DATA, e1, "drop-char")
        after = p.apply(DATA)
        assert b"Beidh" not in after and after.count(b"Simin") == 1
        assert [b.key for b in gs.iter_entries(after, *gs.find_section(after, "living").body)] == [b"2"]

    def test_rename_key_token_only(self):
        p = gs.EditPass()
        for c in gs.iter_entries(DATA, *gs.find_section(DATA, "living").body):
            p.rename_key(DATA, c, "faith", "rite", "faith->rite")
        after = p.apply(DATA)
        assert after.count(b"\trite=12\n") == 2 and b"\tfaith=" not in after
        tokens = [(i, i + 5, b"rite") for i in range(len(DATA)) if DATA.startswith(b"\tfaith=12", i - 1)]
        assert len(tokens) == 2 and after == expected_after(DATA, tokens)
        assert p.counts["faith->rite"].edited == 2

    def test_insert_start_and_end(self):
        e1 = entry(DATA, "living", b"1")
        p = gs.EditPass()
        p.insert(e1, "end", b"\trite=3\n", "add-rite")
        p.insert(e1, "start", b"\n\tethnicity=x", "add-eth")
        after = p.apply(DATA)
        assert after.count(b"rite=3") == 1 and after.count(b"ethnicity=x") == 1
        assert len(after) == len(DATA) + len(b"\trite=3\n") + len(b"\n\tethnicity=x")
        ne = entry(after, "living", b"1")
        kids = [c.key for c in gs.iter_children(after, *ne.body)]
        assert kids[0] == b"ethnicity" and kids[-1] == b"rite"

    def test_two_inserts_same_offset_keep_order(self):
        e1 = entry(DATA, "living", b"1")
        p = gs.EditPass()
        p.insert(e1, "end", b"A", "r")
        p.insert(e1, "end", b"B", "r")
        after = p.apply(DATA)
        assert after[e1.close:e1.close + 3] == b"AB}"

    def test_overlap_refused(self):
        e1 = entry(DATA, "living", b"1")
        p = gs.EditPass()
        p.delete_block(DATA, e1, "a")
        p.rename_key(DATA, e1, "faith", "rite", "b")
        with pytest.raises(gs.GamestateError, match="overlapping"):
            p.apply(DATA)

    def test_bad_insert_position(self):
        with pytest.raises(ValueError):
            gs.EditPass().insert(entry(DATA, "living", b"1"), "middle", b"x", "r")

    def test_empty_pass_is_identity(self):
        assert gs.EditPass().apply(DATA) == DATA


# --------------------------------------------------------------------------- child_at
class TestChildAt:
    def test_resolves_nested_positions(self):
        pos = DATA.index(b"=-5000.1.1")
        mod = DATA.index(b"expiration_date=9999")
        hits = gs.child_at(DATA, [pos, mod])
        parent, child = hits[pos]
        assert parent.key == b"decision_cooldowns" and child.key == b""
        parent, child = hits[mod]
        assert parent.key == b"alive_data" and child.key == b"expiration_date"

    def test_position_inside_a_string_does_not_resolve(self):
        inside = DATA.index(b"not a block")             # inside first_name="Beidh {not a block"
        assert gs.child_at(DATA, [inside]) == {}

    def test_mid_value_position_does_not_resolve(self):
        mid = DATA.index(b"5000.1.1")                   # inside the value, not a child start
        assert gs.child_at(DATA, [mid]) == {}

    def test_entry_block_key_itself(self):
        pos = DATA.index(b"\tdynamic_templates") + 1
        parent, child = gs.child_at(DATA, [pos])[pos]
        assert child.key == b"dynamic_templates" and child.block is not None
        assert parent.open == gs.find_section(DATA, "landed_titles").open

    def test_entry_key_in_a_big_section(self):
        pos = DATA.index(b"2={\n\tfirst_name=\"Simin")     # a living entry's own key
        parent, child = gs.child_at(DATA, [pos])[pos]
        assert child.key == b"2" and DATA[child.block.open:child.block.open + 1] == b"{"

    def test_empty(self):
        assert gs.child_at(DATA, []) == {}

    def test_many_positions_in_one_entry_tokenise_it_once(self, monkeypatch):
        # regression: the first child_at re-tokenised an entry once PER position; on the 1.8.1
        # save's 6 MB artifacts entry R11's ~1,000 positions ran for hours (2026-10-24)
        body = b"".join(b"\tk%d=%d\n" % (i, i) for i in range(2000))
        data = b"meta_data={\n}\nsection={\n\tbig={\n" + body + b"\t}\n}\n"
        positions = [data.index(b"\tk%d=" % i) + 1 for i in range(2000)]
        calls = {"n": 0}
        real = gs.iter_children

        def counting(*a, **k):
            calls["n"] += 1
            return real(*a, **k)

        monkeypatch.setattr(gs, "iter_children", counting)
        hits = gs.child_at(data, positions)
        assert len(hits) == 2000 and all(c.key.startswith(b"k") for _, c in hits.values())
        assert calls["n"] <= 2           # the section body and the entry, each once (old code: 2,000+)

    def test_large_block_is_streamed_and_children_tokenised_once(self, monkeypatch):
        items = b"".join(b"%d={\n\tname=\"n%d\"\n\tmodifiers={ \"\" x }\n\tpad=\"%s\"\n}\n" % (i, i, b"p" * 40)
                         for i in range(4000))
        data = b"meta_data={\n}\nartifacts={\n\tartifacts={\n" + items + b"\t}\n}\n"
        assert len(items) > 256 * 1024            # forces the streamed path
        positions = [m for m in range(len(data)) if data.startswith(b"\tmodifiers=", m - 1) and data[m - 1] == 9]
        calls = {"n": 0}
        real = gs.iter_children

        def counting(*a, **k):
            calls["n"] += 1
            return real(*a, **k)

        monkeypatch.setattr(gs, "iter_children", counting)
        hits = gs.child_at(data, positions)
        assert len(hits) == 4000
        assert calls["n"] <= 4000         # one per item at most, never per position x block size


# --------------------------------------------------------------------------- with savefile
class TestApplyToSave:
    def test_body_pass_roundtrip(self, tmp_path):
        src = tmp_path / "s.ck3"
        src.write_bytes(build_ck3(body=NESTED_BODY))
        save = sf.read_save(src)
        p = gs.EditPass()
        for c in gs.iter_entries(save.gamestate, *gs.find_section(save.gamestate, "living").body):
            p.rename_key(save.gamestate, c, "faith", "rite", "faith->rite")
        expected = p.apply(save.gamestate)
        p.apply_to(save)
        sf.write_save(save, tmp_path / "o.ck3")
        back = sf.read_save(tmp_path / "o.ck3")
        assert back.gamestate == expected and back.meta == DEFAULT_META and back.warnings == []
        assert len(save.edits) == 2

    def test_meta_pass_updates_plaintext_and_length(self, tmp_path):
        src = tmp_path / "s.ck3"
        src.write_bytes(build_ck3(body=NESTED_BODY))
        save = sf.read_save(src)
        meta = gs.find_section(save.gamestate, "meta_data")
        v = gs.find_keys(save.gamestate, meta, "version")[0]
        p = gs.EditPass()
        p.add(gs.Edit(v.value_start, v.value_end, b'"1.20.1.2"', "version-bump"))
        p.apply_to(save)
        sf.write_save(save, tmp_path / "o.ck3")
        back = sf.read_save(tmp_path / "o.ck3")
        assert b'version="1.20.1.2"' in back.meta and back.gamestate.startswith(back.meta)
        assert back.header.meta_len == len(back.meta) == len(DEFAULT_META) + 3


# --------------------------------------------------------------------------- real gamestates (local only)
@pytest.mark.skipif(not REF_GS.exists(), reason="extracted 1.20 reference gamestate not present (gitignored)")
def test_reference_counts_1_20():
    data = REF_GS.read_bytes()
    count = lambda path: sum(1 for _ in gs.iter_entries(data, *gs.locate(data, path).body))
    assert count("landed_titles/landed_titles") == 18371
    assert count("living") == 29977
    assert count("faiths/database") == 103
    assert count("rites/database") == 152


@pytest.mark.skipif(not OLD_GS.exists(), reason="extracted 1.8.1 gamestate not present (gitignored)")
def test_reference_counts_1_8_1():
    data = OLD_GS.read_bytes()
    count = lambda path: sum(1 for _ in gs.iter_entries(data, *gs.locate(data, path).body))
    assert count("living") == 36700
    assert count("landed_titles/landed_titles") == 12702
    assert count("religion/faiths") == 103
