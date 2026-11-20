"""R46: resource-type buildings into the province's 1.21 resource slot (goal 2026-11-19__22-43-27, S5).

CONSEQUENCE: 8 (data) -- the game's 1.21 conversion dropped every quarry, logging camp, orchard and elephant pen of
djdarcy's campaign; a wrong write puts a resource district where the county has no potential, or destroys a district
the game placed.

The concept: only where the county has the trade good's potential; an empty slot gets the district (tier at most 2),
the same district is raised, another district takes the player's answer (default: the minor building inside it, never
a replacement); a second run writes nothing. On the founding campaign's own saves, skipped where absent.
"""
import os
from pathlib import Path

import pytest

from ck3_save_migrator import carry_1_21 as C
from ck3_save_migrator import host_rules as H
from ck3_save_migrator.choices import Asker, parse_auto
from ck3_save_migrator.district_lint import province_facts, stage_two_facts

SAVES = Path(os.environ.get("USERPROFILE", "~")) / "Documents/Paradox Interactive/Crusader Kings III/save games"
CAND, V17 = SAVES / "MIGRATE_TEST__1.21-phase2-update6__v19-candidate.ck3", SAVES / "MIGRATE_TEST__v17.ck3"
GAME = Path(r"E:\SteamLibrary\steamapps\common\Crusader Kings III\game")
pytestmark = pytest.mark.skipif(not (CAND.exists() and V17.exists() and GAME.is_dir()),
                                reason="needs the v19 candidate, the v17 witness and the 1.21 game")


@pytest.fixture(scope="module")
def setup():
    from ck3_save_migrator.savefile import read_save
    H.load.cache_clear()
    host = H.load(str(GAME))
    g, w = read_save(CAND).gamestate, read_save(V17).gamestate
    return host, g, w, stage_two_facts(g, str(GAME), province_facts(g, str(GAME)))


def test_with_the_defaults_districts_raises_and_minor_buildings_and_never_a_replacement(setup):
    host, g, w, facts = setup
    asker = Asker()                                        # no terminal: every question takes the default, m
    r = C.carry_resource_districts(g, host, w, facts, asker)
    assert (len(r.written), len(r.raised), len(r.minor), len(r.replaced)) == (426, 21, 161, 0)
    assert all(p.rsplit("_", 1)[1] in ("1", "2") for _, _, _, p in r.written)          # never above tier 2
    assert {h for *_, h in asker.record} == {"default"} and {a for _, _, a, _ in asker.record} == {"m"}
    f2 = stage_two_facts(r.gamestate, str(GAME), province_facts(r.gamestate, str(GAME)))
    again = C.carry_resource_districts(r.gamestate, host, w, f2, Asker())
    assert (again.written, again.raised, again.minor) == ([], [], [])


def test_keep_leaves_the_games_districts_alone_and_replace_touches_only_a_bare_district(setup):
    host, g, w, facts = setup
    k = C.carry_resource_districts(g, host, w, facts, Asker(auto=parse_auto(["resources=k"])))
    assert (len(k.written), len(k.minor), len(k.replaced)) == (426, 0, 0)
    r = C.carry_resource_districts(g, host, w, facts, Asker(auto=parse_auto(["all=mygame"])))
    assert r.replaced and len(r.minor) == 0
    # the guard: every district replaced held nothing but its own building in the save it came from (red-green
    # 2026-11-20: without this check the guard could be removed and the test still passed)
    import re
    from ck3_save_migrator import gamestate as gs
    D = {e.key.decode(): g[e.open:e.close] for e in gs.iter_entries(g, *gs.locate(g, "districts/database").body) if e.key}
    slot = {e.key.decode(): re.search(rb"\n\t\t\tresource_district=(\d+)", hb)
            for e, _, hb in C._holdings(g)}
    for pid, *_ in r.replaced:
        body = D[slot[pid].group(1).decode()]
        held = [x for x in re.findall(rb"\d+", re.search(rb"buildings=\{([^}]*)\}", body).group(1)) if x != b"4294967295"]
        assert len(held) == 1, (pid, held)
    # every game-placed district in this campaign is bare (the stage-two review: 3,189 of 3,189), so the guard never
    # fires on it; build the case play produces -- a second building in one candidate's district -- and it must be kept
    pid = r.replaced[0][0]
    did = slot[pid].group(1).decode()
    e = next(x for x in gs.iter_entries(g, *gs.locate(g, "districts/database").body) if x.key and x.key.decode() == did)
    bl = re.search(rb"buildings=\{([^}]*)\}", g[e.open:e.close])
    first = re.findall(rb"\d+", bl.group(1))[0]
    at = e.open + bl.end(1)
    g2 = g[:at] + b" " + first + b" " + g[at:]               # the district now lists two buildings
    r2 = C.carry_resource_districts(g2, host, w, stage_two_facts(g2, str(GAME), province_facts(g2, str(GAME))),
                                    Asker(auto=parse_auto(["all=mygame"])))
    assert pid not in {p for p, *_ in r2.replaced}
    assert any(p == pid and "beyond its primary" in why for p, _, why in r2.named)
    assert all("beyond its primary" in why or "potential" in why or "not legal" in why or "several" in why
               or "slot was given" in why for _, _, why in r.named)
