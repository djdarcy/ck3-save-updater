"""The block index behind paths.resolve (S1, 2026-11-02): equal to the descent it replaced, object for object, and
never answering for a gamestate it was not built from.

The founding save's equivalence (0 mismatches over all 1,297,345 positions R5 and R11 hand to resolve) was measured
by tests/one-offs/thinking/poc-block-index/run_poc.py; these tests hold the same contract on the fixtures."""

from __future__ import annotations

import re

import pytest

from ck3_save_migrator.patches import blockindex as BI
from ck3_save_migrator.patches import paths as P
from tests.fixtures.make_ck3 import RULES_BODY
from tests.fixtures.religion import OLD_BODY, REF_BODY

ANY_KEY = re.compile(rb"(?<![^\s{}])([A-Za-z_][\w.]*)[ \t]*=")       # every keyed child's start
ANY_VALUE = re.compile(rb"(?<![^\s{}])([\w.\"-]+)(?=[\s}])")           # every bare token (values included)


def every_position(d: bytes) -> list[int]:
    return sorted({m.start(1) for m in ANY_KEY.finditer(d)} | {m.start(1) for m in ANY_VALUE.finditer(d)})


def same(d: bytes, positions: list[int]):
    BI.forget()
    new, old = P.resolve(d, positions), P.resolve_by_descent(d, positions)
    assert new.keys() == old.keys()
    for p in old:
        assert new[p][0] == old[p][0], p                # the same ancestor Blocks, in order
        assert new[p][1] == old[p][1], p                # the same Child
    return new


@pytest.mark.parametrize("body", [RULES_BODY, OLD_BODY, REF_BODY], ids=["rules", "old", "ref"])
def test_resolve_equals_the_descent_on_every_position_of_a_fixture(body):
    got = same(body, every_position(body))
    assert len(got) > 50                                # the fixture exercises it


def test_a_brace_inside_a_quoted_string_is_not_a_block():
    d = b'x={\n\tname="a{b}c{"\n\ty={\n\t\tz=1\n\t}\n}\nw={ q=2 }\n'
    got = same(d, [d.index(b"z="), d.index(b"q="), d.index(b"y=")])
    assert [b.key for b in got[d.index(b"z=")][0]] == [b"x", b"y"]
    assert [b.key for b in got[d.index(b"q=")][0]] == [b"w"]


def test_a_section_larger_than_the_small_block_limit():
    filler = b"".join(b"\tf%d=%d\n" % (i, i) for i in range(60_000))      # > 256 KB of scalars at depth 1
    d = b"big={\n" + filler + b"\tinner={\n\t\ttype=\"\"\n\t}\n\tother={ type=x }\n}\nsmall={ type=y }\n"
    assert d.index(b"\tinner") > P._SMALL_BLOCK
    same(d, every_position(d))


def test_the_index_belongs_to_one_gamestate_object():
    d = RULES_BODY
    BI.forget()
    a = BI.index_for(d)
    assert BI.index_for(d) is a                         # reused for the same object
    twin = bytes(bytearray(d))
    assert BI.index_for(twin) is not a                  # another object, even with equal bytes, gets its own
    BI.forget()


def test_an_edited_gamestate_is_never_answered_from_the_old_index():
    d = OLD_BODY
    BI.forget()
    P.resolve(d, every_position(d))                     # builds and keeps d's index
    spliced = d[:40] + b"\n\tadded={ a=1 }\n" + d[40:]
    same_after = P.resolve(spliced, every_position(spliced))
    assert same_after == P.resolve_by_descent(spliced, every_position(spliced))
    BI.forget()


# --------------------------------------------------------------------------- the on-disk cache (S1 unit 4)
@pytest.fixture
def cache(tmp_path, monkeypatch):
    """The cache folder in tmp_path; the config's [cache] switch written by each test as it needs."""
    folder = tmp_path / "idx-cache"
    monkeypatch.setenv("CK3UPDATE_CACHE_DIR", str(folder))
    BI.forget()
    yield folder
    BI.forget()


def cache_on(on: bool = True) -> None:
    from ck3_save_migrator.config import config_path
    p = config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"[cache]\nindex = {'true' if on else 'false'}\n", encoding="utf-8")


def arrays(idx):
    return [list(a) for a in (idx.opens, idx.closes, idx.key_starts, idx.key_ends)] + [idx.unclosed]


def test_the_cache_is_on_by_default_and_off_when_turned_off(cache):
    BI.index_for(RULES_BODY)                                         # no [cache] table: on (djdarcy, 2026-11-02)
    assert len(list(cache.glob("*.idx"))) == 1
    BI.forget()
    cache_on(False)
    BI.index_for(OLD_BODY)
    assert len(list(cache.glob("*.idx"))) == 1                       # off: nothing more written


def test_only_the_newest_two_saves_are_kept(cache):
    import os
    import time
    cache_on()
    for i, body in enumerate((RULES_BODY, OLD_BODY, REF_BODY)):
        BI.forget()
        BI.index_for(body)
        for f in cache.glob("*.idx"):                                # make the order of writing the age order
            if f.stat().st_mtime > time.time() - 1:
                os.utime(f, (time.time() - 100 + i, time.time() - 100 + i))
    assert len(list(cache.glob("*.idx"))) == 2
    BI.forget()
    assert BI._load(BI._cache_file(RULES_BODY), RULES_BODY) is None  # the oldest went


def test_the_plan_says_when_it_wrote_the_cache(cache, tmp_path, monkeypatch, capsys):
    from tests.test_update import game, old_save, run
    from ck3_save_migrator import plan as PL
    folder = tmp_path / "save games"
    folder.mkdir()
    monkeypatch.setattr(PL, "save_games_dir", lambda: folder)
    code, out, _ = run(capsys, "status", str(old_save(folder)), "--game-dir", str(game(tmp_path)), "--plain",
                       "--reference", "none")
    assert code == 0 and "wrote this save's block index to" in " ".join(out.split())


def test_a_cached_index_is_read_back_without_building(cache, monkeypatch):
    cache_on()
    built = arrays(BI.index_for(RULES_BODY))
    assert len(list(cache.glob("*.idx"))) == 1
    BI.forget()
    monkeypatch.setattr(BI.BlockIndex, "__init__", lambda self, data: pytest.fail("built instead of read"))
    again = BI.index_for(RULES_BODY)
    assert arrays(again) == built and again.data is RULES_BODY


def test_other_bytes_never_hit(cache):
    cache_on()
    BI.index_for(RULES_BODY)
    BI.forget()
    idx = BI.index_for(OLD_BODY)
    assert idx.data is OLD_BODY and len(list(cache.glob("*.idx"))) == 2
    assert P.resolve(OLD_BODY, every_position(OLD_BODY)) == P.resolve_by_descent(OLD_BODY, every_position(OLD_BODY))


def test_a_damaged_cache_file_is_rebuilt(cache):
    cache_on()
    good = arrays(BI.index_for(RULES_BODY))
    f = next(cache.glob("*.idx"))
    f.write_bytes(f.read_bytes()[:-9])                               # cut short
    BI.forget()
    assert arrays(BI.index_for(RULES_BODY)) == good


def test_entries_older_than_a_day_are_swept_when_one_is_written(cache):
    import os
    import time
    cache_on()
    BI.index_for(RULES_BODY)
    old = next(cache.glob("*.idx"))
    two_days = time.time() - 2 * 24 * 3600
    os.utime(old, (two_days, two_days))
    BI.forget()
    BI.index_for(OLD_BODY)
    assert not old.exists() and len(list(cache.glob("*.idx"))) == 1


def test_cache_clear_and_where(cache, capsys):
    from ck3_save_migrator import cli
    cache_on()
    BI.index_for(RULES_BODY)
    assert cli.main(["cache", "where"]) == 0
    assert "1 cached index(es)" in capsys.readouterr().out
    assert cli.main(["cache", "clear"]) == 0
    assert "removed 1 cached index(es)" in capsys.readouterr().out and not list(cache.glob("*.idx"))


def test_the_cache_switch_survives_a_config_rewrite(cache):
    from ck3_save_migrator import config
    cache_on()
    config.write_disabled(["R21"])                      # disable rewrites the file from the settings it knows
    assert config.index_cache_on() and config.disabled_ids() == ["R21"]


def test_a_bad_cache_setting_is_refused(cache, capsys):
    from ck3_save_migrator import cli
    from ck3_save_migrator.config import config_path
    config_path().parent.mkdir(parents=True, exist_ok=True)
    config_path().write_text('[cache]\nindex = "yes"\n', encoding="utf-8")
    assert cli.main(["cache", "where"]) == 1
    assert "[cache] index must be true or false" in capsys.readouterr().err


def test_unbalanced_text_still_raises_as_before():
    d = b"x={\n\ty={\n\t\tz=1\n}\n"                     # one "}" missing
    from ck3_save_migrator import gamestate as gs
    with pytest.raises(gs.GamestateError):
        P.resolve_by_descent(d, [d.index(b"z=")])
    BI.forget()
    try:
        r = P.resolve(d, [d.index(b"z=")])
    except gs.GamestateError:
        return                                          # raising is the old behaviour too
    pytest.fail(f"the index answered an unbalanced gamestate: {r}")
