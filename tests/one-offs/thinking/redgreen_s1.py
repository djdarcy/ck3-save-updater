"""Red-green audit of S1's new tests (2026-11-02): the detector cache (unit 1) and the block index as the resolver
(unit 3). Each mutation reverts one behaviour, keeping every signature; the named tests must go RED with it and
GREEN after the restore.

The harness is redgreen_status_layout.py's (a fresh bytecode cache per pytest run, so a same-size mutant is never
run from the original's .pyc). The source backup goes to a temporary folder outside the repo this time, so nothing
is left behind to clean up; the source is also held in memory and written back after every mutation and at the end.

Run from the repo root:  python -I tests/one-offs/thinking/redgreen_s1.py
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
D = "tests/test_detect.py"
B = "tests/test_blockindex.py"
MUTATIONS = [
    ("the detector cache never hits", "ck3_save_migrator/detect.py",
     "        if hit is not None and hit[0] is g:\n", "        if False:\n",
     [f"{D}::test_rules_that_share_a_detector_read_the_save_once",
      f"{D}::test_check_reads_a_shared_detector_once"]),
    ("the detector cache keyed by content, not the object", "ck3_save_migrator/detect.py",
     "        if hit is not None and hit[0] is g:\n", "        if hit is not None and hit[0] == g:\n",
     [f"{D}::test_another_gamestate_object_is_judged_again_even_with_the_same_bytes"]),
    ("the index reused for another gamestate", "ck3_save_migrator/patches/blockindex.py",
     "    if _LAST and _LAST[0].data is data:\n", "    if _LAST:\n",
     [f"{B}::test_the_index_belongs_to_one_gamestate_object",
      f"{B}::test_an_edited_gamestate_is_never_answered_from_the_old_index"]),
    ("a value prefix (rgb {) not read as the child's key", "ck3_save_migrator/patches/blockindex.py",
     "_KEY_BEFORE = re.compile(rb'([^\\s{}=]+)[ \\t]*=[ \\t]*(?:(?:' + _PREFIX + rb')[ \\t]*)?$')\n",
     "_KEY_BEFORE = re.compile(rb'([^\\s{}=]+)[ \\t]*=[ \\t]*$')\n",
     [f"{B}::test_resolve_equals_the_descent_on_every_position_of_a_fixture"]),
    ("braces inside quoted strings counted as blocks", "ck3_save_migrator/patches/blockindex.py",
     "_TOKEN = re.compile(rb'\"(?:[^\"\\\\]|\\\\.)*\"|[{}]')\n", "_TOKEN = re.compile(rb'[{}]')\n",
     [f"{B}::test_a_brace_inside_a_quoted_string_is_not_a_block"]),
    ("an unclosed brace answered instead of refused", "ck3_save_migrator/patches/blockindex.py",
     "        if self.unclosed:\n", "        if False:\n",
     [f"{B}::test_unbalanced_text_still_raises_as_before"]),
    ("unit 4: the cache never read", "ck3_save_migrator/patches/blockindex.py",
     "    idx = _load(_cache_file(data), data) if use_cache else None\n", "    idx = None\n",
     [f"{B}::test_a_cached_index_is_read_back_without_building"]),
    ("unit 4: the key ignores the bytes", "ck3_save_migrator/patches/blockindex.py",
     '    return cache_dir() / f"{hashlib.sha256(data).hexdigest()}-v{CACHE_VERSION}.idx"\n',
     '    return cache_dir() / f"index-v{CACHE_VERSION}.idx"\n',
     [f"{B}::test_other_bytes_never_hit"]),
    ("unit 4: no sweep", "ck3_save_migrator/patches/blockindex.py",
     "            if old != path and now - old.stat().st_mtime > SWEEP_SECONDS:\n",
     "            if False:\n", [f"{B}::test_entries_older_than_a_day_are_swept_when_one_is_written"]),
    ("unit 4: on by default", "ck3_save_migrator/config.py",
     '    return bool(read_config(path).get("cache", {}).get("index", False))\n',
     '    return bool(read_config(path).get("cache", {}).get("index", True))\n',
     [f"{B}::test_the_cache_is_off_unless_turned_on"]),
    ("a large parent read like a small one", "ck3_save_migrator/patches/paths.py",
     "        if parent.close - parent.open <= _SMALL_BLOCK:\n            for c in gs.iter_children(data, *parent.body):\n                if c.key_start in want:\n",
     "        if True:\n            for c in gs.iter_children(data, *parent.body):\n                if c.key_start in want:\n",
     [f"{B}::test_a_section_larger_than_the_small_block_limit"]),
]


def pytest(tests):
    with tempfile.TemporaryDirectory(prefix="rg-pyc-") as pyc:
        r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *tests], cwd=ROOT,
                           capture_output=True, text=True, timeout=600,
                           env={**os.environ, "PYTHONPYCACHEPREFIX": pyc})
    return r.returncode, r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr[-300:]


def main() -> int:
    files = sorted({m[1] for m in MUTATIONS})
    original = {f: (ROOT / f).read_bytes() for f in files}
    bad = 0
    with tempfile.TemporaryDirectory(prefix="rg-backup-") as backup:
        for f in files:
            shutil.copy2(ROOT / f, Path(backup) / Path(f).name)
        try:
            for name, f, old, new, tests in MUTATIONS:
                src = original[f].decode("utf-8")
                if "\r\n" in src:                                  # a CRLF checkout: match its line ends
                    old, new = old.replace("\n", "\r\n"), new.replace("\n", "\r\n")
                assert src.count(old) == 1, f"{name}: anchor found {src.count(old)} times"
                (ROOT / f).write_bytes(src.replace(old, new).encode("utf-8"))
                red, red_line = pytest(tests)
                (ROOT / f).write_bytes(original[f])
                green, green_line = pytest(tests)
                ok = red != 0 and green == 0
                bad += not ok
                print(f"{'OK  ' if ok else 'FAIL'} {name}: mutated -> {red_line} | restored -> {green_line}")
        finally:
            for f in files:
                (ROOT / f).write_bytes(original[f])
        restored = all((ROOT / f).read_bytes() == (Path(backup) / Path(f).name).read_bytes() for f in files)
    print("source restored and equal to the backup:", restored)
    return 1 if bad or not restored else 0


if __name__ == "__main__":
    sys.exit(main())
