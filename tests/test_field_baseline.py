"""Field baselines (ck3_save_migrator/baselines.py): structure only, deterministic, keyed by game version."""

from __future__ import annotations

import json

from ck3_save_migrator import baselines as B
from ck3_save_migrator._vendor.savediff import keys as K

META = b'meta_data={\n\tsave_game_version=18\n\tversion="1.20.1.2"\n}\n'


def save(faiths: int = 3) -> bytes:
    body = "".join(f'\t\t{i}={{\n\t\t\tfaith_type=type_{i}\t\t\treligion=0\n\t\t\tname="Faith {i}"\n'
                   f'\t\t\tholy_sites={{ }}\n\t\t}}\n' for i in range(faiths))
    return META + ("religion={\n\tfaiths={\n" + body + "\t}\n}\n").encode()


def test_baseline_holds_field_shares_and_no_values():
    b = B.build_baseline(save(), min_entries=3)
    db = b["databases"]["religion/faiths"]
    assert b["game_version"] == "1.20.1.2" and db["entries"] == 3
    assert db["fields"] == {"faith_type": [1.0, 0.0], "holy_sites": [1.0, 1.0], "name": [1.0, 0.0],
                            "religion": [1.0, 0.0]}
    text = B.dumps(b)
    for value in ("type_0", "Faith 1", '"0"'):
        assert value not in text, f"a value leaked into the baseline: {value}"


def test_baseline_is_deterministic():
    assert B.dumps(B.build_baseline(save(), 3)) == B.dumps(B.build_baseline(save(), 3))


def test_game_version_is_read_from_meta_data():
    assert B.game_version(META + b"x=1\n") == "1.20.1.2"
    assert B.game_version(b"living={\n}\n") is None


def test_load_baseline_returns_none_for_a_version_that_ships_none():
    assert B.load_baseline("0.0.0.0") is None and B.load_baseline(None) is None


def test_the_shipped_1_20_1_2_baseline_loads_and_records_faith_type_on_every_faith():
    b = B.load_baseline("1.20.1.2")
    assert b is not None and b["game_version"] == "1.20.1.2" and "1.20.1.2" in B.shipped_versions()
    assert b["databases"]["faiths/database"]["fields"]["faith_type"] == [1.0, 0.0]
    # the game's own rites made in play carry no rite_type (reference rites 150 and 151): under 1.0, by measurement
    assert b["databases"]["rites/database"]["fields"]["rite_type"][0] < 1.0


def test_as_coverage_feeds_coverage_gaps_as_the_witness():
    # F25 against the baseline: our faith 1 leaves faith_type empty, every faith in the game's own save carries it
    b = B.build_baseline(save(), 3)
    ours = K.field_coverage(*_g_idx(META + b'religion={\n\tfaiths={\n\t\t0={\n\t\t\tfaith_type=x\n\t\t\treligion=0\n'
                                           b'\t\t\tname="a"\n\t\t}\n\t\t1={\n\t\t\tfaith_type=""\n\t\t\treligion=0\n'
                                           b'\t\t\tname="b"\n\t\t}\n\t}\n}\n'), "religion/faiths")
    rows = K.coverage_gaps(ours, B.as_coverage(b, "religion/faiths"))
    assert [(r["field"], r["missing"], r["empty"]) for r in rows] == [("faith_type", 0, 1)]
    assert B.as_coverage(b, "nowhere")["entries"] == 0


def test_dumps_writes_every_level_in_sorted_key_order():
    # the shipped file must regenerate byte for byte on any machine: key order fixed at every level, not insertion
    text = B.dumps(B.build_baseline(save(), 3))
    assert text == json.dumps(json.loads(text), indent=1, sort_keys=True) + "\n"
    assert B.load_baseline("1.20.1.2") is not None


def test_shipped_baseline_field_names_are_identifiers_never_ids_or_values():
    import re
    b = B.load_baseline("1.20.1.2")
    names = {k for d in b["databases"].values() for k in d["fields"]}
    assert names and all(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*", k) for k in names)


def test_as_coverage_rebuilds_counts_by_rounding_not_truncating():
    # 1 of 3 entries is a share of 0.3333 once rounded; 0.3333 * 3 = 0.9999 must give back 1 entry, not 0, or the
    # check would report a gap the game's own save does not have (mutation M10, 2026-11-16)
    b = {"databases": {"x": {"entries": 3, "fields": {"a": [0.3333, 0.3333]}}}}
    f = B.as_coverage(b, "x")["fields"]["a"]
    assert (f["present"], f["empty"]) == (1, 1)


def test_as_coverage_of_a_baseline_without_databases_is_empty():
    assert B.as_coverage({}, "faiths/database")["entries"] == 0          # mutation M11


def test_shipped_versions_lists_only_folders_holding_fields_json(tmp_path, monkeypatch):
    # a version folder without its fields.json, or a stray file, is not a shipped baseline (mutation M9)
    (tmp_path / "baselines" / "1.20.1.2").mkdir(parents=True)
    (tmp_path / "baselines" / "1.20.1.2" / "fields.json").write_text("{}", encoding="utf-8")
    (tmp_path / "baselines" / "9.9.9").mkdir()
    (tmp_path / "baselines" / "README.txt").write_text("x", encoding="utf-8")
    monkeypatch.setattr(B.resources, "files", lambda pkg: tmp_path)
    assert B.shipped_versions() == ["1.20.1.2"]


def test_baseline_shares_keep_four_places_for_a_partial_field():
    # a field on 1 of 3 entries is 0.3333, not 0 (round to whole numbers would erase every partial share: R3)
    g = META + (b"religion={\n\tfaiths={\n\t\t0={\n\t\t\tname=a\n\t\t\ttag=x\n\t\t}\n\t\t1={\n\t\t\tname=b\n\t\t}\n"
                b"\t\t2={\n\t\t\tname=c\n\t\t}\n\t}\n}\n")
    assert B.build_baseline(g, 3)["databases"]["religion/faiths"]["fields"]["tag"] == [0.3333, 0.0]


def test_load_baseline_of_a_corrupt_file_is_none(tmp_path, monkeypatch):
    (tmp_path / "baselines" / "1.20.1.2").mkdir(parents=True)
    (tmp_path / "baselines" / "1.20.1.2" / "fields.json").write_text("{ not json", encoding="utf-8")
    monkeypatch.setattr(B.resources, "files", lambda pkg: tmp_path)
    assert B.load_baseline("1.20.1.2") is None                          # R6


def test_shipped_versions_are_sorted_whatever_order_the_folder_lists_them(tmp_path, monkeypatch):
    # on Linux a folder lists in no fixed order; the version list must not depend on it (R8)
    for v in ("1.9.0", "1.20.1.2", "1.10.0"):
        (tmp_path / "baselines" / v).mkdir(parents=True)
        (tmp_path / "baselines" / v / "fields.json").write_text("{}", encoding="utf-8")

    class Root:
        def joinpath(self, name):
            d = tmp_path / name

            class Listing:
                def iterdir(self):
                    return iter(sorted(d.iterdir(), reverse=True))
            return Listing()

    monkeypatch.setattr(B.resources, "files", lambda pkg: Root())
    assert B.shipped_versions() == sorted(["1.9.0", "1.20.1.2", "1.10.0"])


def _g_idx(g: bytes):
    from ck3_save_migrator._vendor.savediff import text as T
    return g, T.SectionIndex(g)
