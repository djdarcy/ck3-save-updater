"""savediff against the probe it was lifted from (tests/one-offs/shape_diff.py), on one synthetic three-witness save.

The probe is the reference implementation: the library's ``shape()`` must equal the probe's on every path and every
field, and the library's primitives must rebuild the probe's ``keys()`` census and the counts of its keyed gaps.
``census()`` below is that rebuild; it documents how a caller gets the three-witness numbers from the library.

The witnesses, as in the probe: ``ref`` (a 1.20 save at the campaign's date), ``chain`` (the campaign as the game
itself converted it) and ``ours`` (the migrated campaign). ``ours`` holds the ref's new-map titles at a slot offset of
+1000, its own campaign titles, a few at other offsets or generations; the campaign characters ``ours`` shares with
``chain``, and some ref characters translated into ``ours`` at 1 + the highest campaign slot.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from ck3_save_migrator._vendor.savediff import ids as IDS
from ck3_save_migrator._vendor.savediff import keys as K
from ck3_save_migrator._vendor.savediff import shape as S
from ck3_save_migrator._vendor.savediff import text as T

PROBE_PATH = Path(__file__).resolve().parent / "one-offs" / "shape_diff.py"
TITLES = "landed_titles/landed_titles"
CHARACTERS = ("living", "dead_unprunable", "characters/dead_prunable")


@pytest.fixture(scope="module")
def probe():
    spec = importlib.util.spec_from_file_location("shape_diff_probe", PROBE_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod            # dataclasses look their module up while the class is built
    try:
        spec.loader.exec_module(mod)
        yield mod
    finally:
        sys.modules.pop(spec.name, None)


# --------------------------------------------------------------------------- the synthetic triple
def _title(i: int, key: str, quoted: bool = False, history: bool = False) -> str:
    h = "\thistory={\n\t\tkey=old_name\n\t\t1066.1.1=yes\n\t}\n" if history else ""
    k = f'"{key}"' if quoted else key
    return f"{i}={{\n{h}\tkey={k}\n\tname=\"T {{ {key}\"\n\tholder=1\n}}\n"


def _chars(ids, extra: str = "") -> str:
    return "".join(f"{i}={{\n\tfirst_name=\"P\"\n\tbirth=950.1.1\n}}\n" for i in ids) + extra


def _db(name: str, body: str) -> str:
    return f"{name}={{\n{body}}}\n"


CAMPAIGN = ["k_a", "d_b", "c_c", "b_d", "b_e"]
NEW_MAP = ["c_new1", "b_new1", "b_new2", "c_new2", "d_new3", "e_new4", "k_new5", "b_new6"]


def build(witness: str) -> bytes:
    """One witness of the triple, as a gamestate."""
    t = []
    if witness == "ref":
        t += [_title(20 + n, k, quoted=n % 2 == 0) for n, k in enumerate(CAMPAIGN)]       # campaign keys, other ids
        t += [_title(30 + n, k, history=n == 0) for n, k in enumerate(NEW_MAP)]
        t += [_title(40, "b_odd"), _title(IDS.make(41, 1), "b_gen"), _title(50, "b_lost"), _title(51, "c_lost")]
    else:
        t += [_title(n, k, quoted=witness == "chain") for n, k in enumerate(CAMPAIGN)]
        t += [_title(5, "x_x_1"), _title(6, "c_camp")]
        if witness == "ours":
            t += [_title(1030 + n, k, history=n == 0) for n, k in enumerate(NEW_MAP)]      # the transplant, +1000
            t += [_title(1500, "b_odd"), _title(IDS.make(1041, 0), "b_gen")]                  # other offset / generation
    titles = "landed_titles={\n\tlanded_titles={\n" + "".join(t) + "\t}\n\tindex=1600\n}\n"

    campaign_living, campaign_dead, campaign_pruned = [1, 2, 3, 4, 5], [6, 7, 8], [9, 10, IDS.make(11, 1)]
    if witness == "ref":
        living, dead, pruned = [1, 2, 3, 4, 100, 101, 102, 103, IDS.make(107, 1)], [104, 105], [106]
    else:
        living, dead, pruned = list(campaign_living), list(campaign_dead), list(campaign_pruned)
        if witness == "chain":
            dead.append(200)                                                     # a chain-only death
        if witness == "ours":
            off = 12                                                             # 1 + highest campaign slot (11)
            living += [IDS.translate(r, off) for r in (100, 101, 102, 105, IDS.make(107, 1))]
            dead += [IDS.translate(104, off)]
    dead_section = _db("dead_unprunable", _chars(dead))
    chars = (_db("living", _chars(living, "50=none\n")) + dead_section
             + "characters={\n\tdead_prunable={\n" + _chars(pruned) + "\t}\n}\n")
    if witness == "ours":
        chars += dead_section                                                    # 1.20 writes it twice

    n_prov = {"ref": list(range(1, 61)), "chain": list(range(1, 58)), "ours": list(range(1, 56)) + [58]}[witness]
    provinces = _db("provinces", "".join(f"{p}={{\n\tculture=3\n}}\n" for p in n_prov) + "\tsub={\n\t\tx=1\n\t}\n")

    counties = {"ref": ["c_c", "c_new1", "c_new2", "c_lost"], "chain": ["c_c", "c_new2"],
                "ours": ["c_c", "c_new1", "c_camp"]}[witness]
    county_manager = ("county_manager={\n\tcounties={\n"
                      + "".join(f"\t\t{c}={{\n\t\t\tdevelopment=4\n\t\t}}\n" for c in counties) + "\t}\n}\n")
    names = {"ref": "k_a=1 c_new1=2 b_new2=3 other_name=4", "chain": "k_a=1 b_new2=3",
             "ours": "k_a=1 c_new1=2"}[witness]
    coats = ("coat_of_arms={\n\tcoat_of_arms_manager_database={\n1={\n\tpattern=\"a\"\n}\n\t}\n"
             "\tcoat_of_arms_manager_name_map={\n" + "".join(f"\t\t{p}\n" for p in names.split()) + "\t}\n"
             "\tnext_id=5\n}\n")
    lookup = {"ref": "han_1176=100\n188854bis=101\n500=103\n600=2\n", "chain": "500=1\n",
              "ours": "han_1176=112\n500=1\n"}[witness]
    strategies = {"ref": [1, 100, 103], "chain": [1, 2], "ours": [1, 112]}[witness]
    ai = "ai={\n\tai_strategies={\n" + _chars(strategies) + "\t}\n}\n"
    variables = "variables={\n\tdata={\n\t\t{\n\t\t\tflag=a\n\t\t}\n\t\t{\n\t\t\tflag=b\n\t\t}\n\t}\n\tlist={ 1 2 3 }\n}\n"
    meta = 'meta_data={\n\tversion="1.20.1.2"\n\tsave_game_version=18\n}\n'
    return (meta + titles + chars + provinces + county_manager + coats + "character_lookup={\n" + lookup + "}\n"
            + ai + variables).encode()


@pytest.fixture(scope="module")
def g3() -> dict[str, bytes]:
    return {n: build(n) for n in ("ref", "chain", "ours")}


# --------------------------------------------------------------------------- the census, from the library
def census(g3: dict[str, bytes]) -> dict:
    """The probe's three-witness numbers, rebuilt from savediff's primitives (the wiring a caller writes)."""
    idx = {n: T.SectionIndex(g) for n, g in g3.items()}
    tk = {n: K.field_keys(g, idx[n], TITLES) for n, g in g3.items()}
    tid = {n: {k: i for i, k in m.items()} for n, m in tk.items()}
    title_offset, new_titles = IDS.offset_by_mode(tid["ref"], tid["ours"])
    ch = {n: K.union_keys(g, idx[n], CHARACTERS) for n, g in g3.items()}
    campaign = ch["ours"] & ch["chain"]
    char_offset = 1 + max(IDS.slot(i) for i in campaign)
    new_chars_ref = {r for r in ch["ref"] if IDS.translate(r, char_offset) in ch["ours"]}
    provinces = {n: K.entry_keys(g, idx[n], "provinces") for n, g in g3.items()}
    sh = {n: S.shape(g) for n, g in g3.items()}

    gaps = {}
    title_sets = {
        "county_manager/counties": {n: sh[n]["county_manager/counties"].keys for n in g3},
        "coat_of_arms/coat_of_arms_manager_name_map (title keys)":
            {n: {k for k in sh[n]["coat_of_arms/coat_of_arms_manager_name_map"].keys if S.TITLE_KEY.match(k)}
             for n in g3},
        f"{TITLES} (by key=)": {n: set(tk[n].values()) for n in g3},
    }
    for name, sets in title_sets.items():
        gp = K.key_gaps(sets, have="ours", want="ref", split=new_titles)
        gaps[name] = (gp["in_split"]["count"], gp["rest"]["count"])
    gp = K.key_gaps(provinces, have="ours", want="ref", split=provinces["ref"])     # every province lack is new-map
    gaps["provinces"] = (gp["in_split"]["count"], gp["rest"]["count"])
    for path in ("living", "dead_unprunable", "ai/ai_strategies"):
        s = {n: K.entry_keys(g, idx[n], path) for n, g in g3.items()}
        # new-map: the copied ref ids, translated into ours, that ours lacks in this section
        translated = {IDS.translate(r, char_offset) for r in s["ref"] & new_chars_ref}
        new = K.key_gaps({"ours": s["ours"], "ref in ours": translated}, have="ours", want="ref in ours")
        # campaign: the probe counts every ref id that was not copied, whether or not ours has a version of it
        camp = K.key_gaps({"none": set(), "ref": s["ref"]}, have="none", want="ref", split=new_chars_ref)
        gaps[path] = (new["rest"]["count"], camp["rest"]["count"])
    maps = {n: K.scalar_map(g, idx[n], "character_lookup") for n, g in g3.items()}
    copied = {k for k, v in maps["ref"].items() if v in new_chars_ref}
    gp = K.key_gaps({n: set(m) for n, m in maps.items()}, have="ours", want="ref", split=copied)
    gaps["character_lookup"] = (gp["in_split"]["count"], gp["rest"]["count"])
    return {"title_offset": title_offset, "char_offset": char_offset, "new_titles": new_titles,
            "new_chars_ref": new_chars_ref, "provinces": provinces, "gaps": gaps}


# --------------------------------------------------------------------------- the equivalence
@pytest.mark.parametrize("witness", ["ref", "chain", "ours"])
def test_shape_equals_the_probes_on_every_path_and_field(probe, g3, witness):
    mine, theirs = S.shape(g3[witness]), probe.shape(g3[witness])
    assert set(mine) == set(theirs)
    for path in theirs:
        a, b = mine[path], theirs[path]
        assert (a.size, a.kinds, a.keys, a.repeats) == (b.size, b.kinds, b.keys, b.repeats), path


def test_the_triple_exercises_what_it_should(g3):
    """The fixture is not trivial: a repeated section, a database over the threshold, freed slots, scalars."""
    sh = S.shape(g3["ours"])
    assert sh["dead_unprunable"].repeats == 2 and sh["provinces"].kinds["num"] > 50 and "provinces/sub" not in sh
    assert sh["living"].kinds["free"] == 1 and sh["character_lookup"].kinds["scalar:other"] == 1
    assert "variables/data" in sh and sh["variables/data"].kinds["anon"] == 2


def test_the_census_reproduces_the_probes_keys(probe, g3):
    theirs, mine = probe.keys(g3), census(g3)
    assert (mine["title_offset"], mine["char_offset"]) == (theirs.title_offset, theirs.char_offset) == (1000, 12)
    assert mine["new_titles"] == theirs.new_titles == set(NEW_MAP)
    assert mine["new_chars_ref"] == theirs.new_chars_ref == {100, 101, 102, 104, 105, IDS.make(107, 1)}
    assert mine["provinces"] == theirs.provinces


def test_the_census_reproduces_the_probes_keyed_gaps(probe, g3):
    K3 = probe.keys(g3)
    rows = probe.keyed_gaps(g3, {n: probe.shape(g) for n, g in g3.items()}, K3)
    theirs = {r["section"]: (r["lack_new_map"], r["lack_campaign"]) for r in rows}
    mine = census(g3)["gaps"]
    assert mine == theirs
    # and the numbers are not all zero: the comparison has something to find
    assert theirs["county_manager/counties"] == (1, 1) and theirs["character_lookup"] == (1, 1)
    assert theirs["dead_unprunable"][0] == 1 and theirs["provinces"] == (4, 0)
