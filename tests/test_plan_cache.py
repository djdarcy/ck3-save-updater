"""The checks' verdicts kept between `status` and `update` (0.4.30, plancache.py; design 2026-11-06 21:10, djdarcy: "I
think a lot of people are going to wonder why they have to redo the same exact process twice"). Only a "needed"
verdict is reused; a different save, a changed input or the switch turned off means a fresh run."""

from __future__ import annotations

import json

import pytest

from ck3_save_migrator import cli, config, detect, plancache
from tests import test_update as TU
from tests.test_update import game, old_save, ref_save, run

saves = TU.saves


@pytest.fixture
def cache_on(monkeypatch):
    monkeypatch.setattr(config, "plan_cache_on", lambda path=None: True)


@pytest.fixture
def calls(monkeypatch):
    """Every detector run, by rule id."""
    seen = []
    real = detect.detect

    def counting(rid, g, env):
        seen.append(rid)
        return real(rid, g, env)
    monkeypatch.setattr(detect, "detect", counting)
    return seen


def _status_then_update(tmp_path, saves, capsys, calls, *update_flags):
    s, g = old_save(saves), game(tmp_path)
    ref_save(saves, "Ref.ck3", bookmark=True)
    assert run(capsys, "status", str(s), "--game-dir", str(g))[0] == 0
    first = list(calls)
    calls.clear()
    code, out, _ = run(capsys, "update", str(s), "--game-dir", str(g), "--dry-run", "--no-lint", "--wos-shape",
                       "faith", *update_flags)
    assert code == 0
    return first, list(calls), out


def test_update_after_status_reuses_the_needed_verdicts_and_checks_the_rest(tmp_path, saves, capsys, cache_on,
                                                                              calls):
    first, second, out = _status_then_update(tmp_path, saves, capsys, calls)
    st, up = cli.LAST_PLAN["status"], cli.LAST_PLAN["update"]
    needed = {s.id for s in st.steps if s.reason.startswith("needed")}
    assert needed and not needed & set(second)                        # no "needed" verdict was judged again
    assert set(second) == set(first) - needed                         # everything else was
    assert [(x.id, x.will_run, x.reason) for x in up.steps] == [(x.id, x.will_run, x.reason) for x in st.steps]
    assert f"reused {len(needed)} verdict(s)" in out


def test_a_cached_done_verdict_is_judged_again(tmp_path, saves, capsys, cache_on, calls):
    s, g = old_save(saves), game(tmp_path)
    ref_save(saves, "Ref.ck3", bookmark=True)
    run(capsys, "status", str(s), "--game-dir", str(g))
    f = next(plancache.cache_dir().glob("*.json"))
    body = json.loads(f.read_text(encoding="utf-8"))
    rid = next(r for r, v in body["verdicts"].items() if v["state"] == "needed")
    body["verdicts"][rid]["state"] = "done"                            # pretend status had found it done
    f.write_text(json.dumps(body), encoding="utf-8")
    calls.clear()
    run(capsys, "update", str(s), "--game-dir", str(g), "--dry-run", "--no-lint", "--wos-shape", "faith")
    assert rid in calls


def test_a_changed_input_means_a_fresh_run(tmp_path, saves, capsys, cache_on, calls):
    first, second, out = _status_then_update(tmp_path, saves, capsys, calls, "--face-changes", "none")
    assert sorted(second) == sorted(first) and "reused" not in out


def _status_then_changed_update(tmp_path, saves, capsys, calls, change):
    """status, then ``change()`` (a new save in the same file, another build of the tool), then update."""
    s, g = old_save(saves), game(tmp_path)
    ref_save(saves, "Ref.ck3", bookmark=True)
    assert run(capsys, "status", str(s), "--game-dir", str(g))[0] == 0
    first = list(calls)
    calls.clear()
    change()
    code, out, _ = run(capsys, "update", str(s), "--game-dir", str(g), "--dry-run", "--no-lint", "--wos-shape",
                       "faith")
    assert code == 0
    return first, list(calls), out


def test_a_different_save_in_the_same_file_means_a_fresh_run(tmp_path, saves, capsys, cache_on, calls):
    """djdarcy 2026-11-06: "if the file is a DIFFERENT save ... nothing changed (presumably the save's content
    hash)". The file's name is the same; its gamestate is not."""
    first, second, out = _status_then_changed_update(
        tmp_path, saves, capsys, calls, lambda: old_save(saves, body_extra=b"played_on=1\n"))
    assert sorted(second) == sorted(first) and "reused" not in out


def test_another_build_of_the_tool_means_a_fresh_run(tmp_path, saves, capsys, cache_on, calls, monkeypatch):
    """An upgrade or a local edit changes the code fingerprint, and no verdict of the old code is reused."""
    first, second, out = _status_then_changed_update(
        tmp_path, saves, capsys, calls,
        lambda: monkeypatch.setattr(plancache, "code_fingerprint", lambda: "another build"))
    assert sorted(second) == sorted(first) and "reused" not in out


def test_the_switch_off_writes_and_reuses_nothing(tmp_path, saves, capsys, calls):
    first, second, out = _status_then_update(tmp_path, saves, capsys, calls)       # the cache is off in tests
    assert sorted(second) == sorted(first) and "reused" not in out
    assert not list(plancache.cache_dir().glob("*.json"))


def test_cache_clear_removes_the_verdicts(tmp_path, saves, capsys, cache_on):
    s, g = old_save(saves), game(tmp_path)
    ref_save(saves, "Ref.ck3", bookmark=True)
    run(capsys, "status", str(s), "--game-dir", str(g))
    assert list(plancache.cache_dir().glob("*.json"))
    code, out, _ = run(capsys, "cache", "clear")
    assert code == 0 and "saved plan verdict file(s)" in out and not list(plancache.cache_dir().glob("*.json"))
