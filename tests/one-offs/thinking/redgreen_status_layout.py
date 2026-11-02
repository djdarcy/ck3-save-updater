"""Red-green audit of the status layout / spinner / timing / fail-early unit (2026-11-01).

Each mutation reverts one behaviour; the named tests must go RED with it and GREEN after the restore. The source is
kept in memory AND in a backup file beside this script; it is written back after every mutation and compared at the
end. Nothing here deletes, spawns daemons or touches a path outside the repo: the mutated code only reads saves.

Run from the repo root:  python -I tests/one-offs/thinking/redgreen_status_layout.py
"""

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
T = "tests/test_status_layout.py"
MUTATIONS = [
    ("fail early off", "ck3_save_migrator/plan.py", "    refused = bool(refusals)\n", "    refused = False\n",
     [f"{T}::test_a_refused_plan_does_not_read_the_whole_save",
      f"{T}::test_a_gap_nothing_covers_refuses_before_the_full_read"]),
    ("uncovered gap checked after the read", "ck3_save_migrator/plan.py",
     "    if gv and sv[\"version\"] and not same_line and not covered and not refusals:\n",
     "    if False:\n", [f"{T}::test_a_gap_nothing_covers_refuses_before_the_full_read"]),
    ("spinner never erases", "ck3_save_migrator/spinner.py",
     '                self.stream.write("\\r" + " " * self._drawn + "\\r")\n', "                pass\n",
     [f"{T}::test_the_spinner_draws_the_stage_and_erases_itself",
      f"{T}::test_an_error_inside_the_detectors_stops_the_spinner_and_leaves_the_line_clean"]),
    ("spinner ignores NO_COLOR", "ck3_save_migrator/spinner.py",
     '    if plain or quiet > 0 or json_out or os.environ.get("NO_COLOR", "") != "":\n',
     "    if plain or quiet > 0 or json_out:\n",
     [f"{T}::test_the_spinner_is_wanted_only_on_a_terminal_and_never_under_plain_quiet_json_or_no_color"]),
    ("--plain keeps colour", "ck3_save_migrator/cli.py",
     '    return Paint(C.should_use_color(stream) and not RUN["plain"])\n',
     "    return Paint(C.should_use_color(stream))\n",
     [f"{T}::test_plain_and_no_color_give_the_same_text_with_no_escape_and_no_spinner"]),
    ("the verdict does not wrap", "ck3_save_migrator/plan.py",
     "            got = wrap_segments(segs, c, width - len(word) - 2)\n",
     "            got = wrap_segments(segs, c, 10_000)\n",
     [f"{T}::test_no_line_is_wider_than_the_width_and_nothing_wraps_under_a_header"]),
    ("a bullet wraps under its dash", "ck3_save_migrator/plan.py",
     '            bullet = "- " if isinstance(value, str) and value.startswith("- ") else ""    # wraps under its text\n',
     '            bullet = ""\n', [f"{T}::test_a_long_value_wraps_under_its_own_column"]),
    ("no seed row", "ck3_save_migrator/plan.py", "        if self.seed:\n", "        if False:\n",
     [f"{T}::test_the_save_block_names_the_seed"]),
    ("timings not kept", "ck3_save_migrator/plan.py", "                timings[rid] = time.perf_counter() - t\n",
     "                pass\n",
     [f"{T}::test_the_progress_names_each_stage_in_order_and_the_timings_cover_each_judged_step"]),
    ("compact spacing ignored", "ck3_save_migrator/plan.py",
     '    return int(layout.get("gap", GAP)), layout.get("spacing", SPACING) != "compact"\n',
     '    return int(layout.get("gap", GAP)), True\n',
     [f"{T}::test_compact_spacing_leaves_no_blank_line_and_the_same_lines_otherwise"]),
    ("the gap setting ignored", "ck3_save_migrator/plan.py",
     '    return int(layout.get("gap", GAP)), layout.get("spacing", SPACING) != "compact"\n',
     '    return GAP, layout.get("spacing", SPACING) != "compact"\n',
     [f"{T}::test_the_gap_is_the_spaces_between_the_header_column_and_the_longest_field"]),
    ("a config rewrite drops [display]", "ck3_save_migrator/config.py",
     '    if data.get("display"):          # kept as written: the player\'s own layout choices\n',
     "    if False:\n", [f"{T}::test_the_display_settings_survive_a_config_rewrite"]),
    ("flow never mirrors the block above", "ck3_save_migrator/plan.py",
     "            out.append(n if len(rows) > 1 or not out else max(n, out[-1]))\n", "            out.append(n)\n",
     [f"{T}::test_the_value_columns_of_each_align", f"{T}::test_the_layout_example_in_docs_config_is_what_the_renderer_prints"]),
    ("global uses each block's own column", "ck3_save_migrator/plan.py",
     "        return [max(natural, default=0)] * len(blocks)\n", "        return natural\n",
     [f"{T}::test_every_row_puts_its_colon_two_before_its_blocks_value_column"]),
    # batch 2 (the /test-redgreen pass of the 0.3.19 last-mile): the tests the first 15 did not reach
    ("a bad gap is accepted", "ck3_save_migrator/config.py",
     "    if not isinstance(gap, int) or isinstance(gap, bool) or not 1 <= gap <= 8:\n", "    if False:\n",
     [f"{T}::test_a_bad_display_setting_is_refused_naming_the_file"]),
    ("a bad spacing or align is accepted", "ck3_save_migrator/config.py",
     '    for key, allowed in (("spacing", SPACINGS), ("align", ALIGNS)):\n', "    for key, allowed in ():\n",
     [f"{T}::test_a_bad_align_is_refused", f"{T}::test_a_bad_display_setting_is_refused_naming_the_file"]),
    ("no ASCII fallback", "ck3_save_migrator/spinner.py",
     '        "".join(theme["frames"]).encode(getattr(stream, "encoding", None) or "ascii")\n', "        pass\n",
     [f"{T}::test_the_spinner_falls_back_to_ascii_on_a_stream_that_cannot_write_its_frames"]),
    ("a disabled spinner still starts", "ck3_save_migrator/spinner.py",
     "        if self.enabled:\n            self._t0 = time.perf_counter()\n",
     "        if True:\n            self._t0 = time.perf_counter()\n",
     [f"{T}::test_a_disabled_spinner_writes_nothing_and_starts_no_thread"]),
    ("the old defaults", "ck3_save_migrator/config.py",
     'DISPLAY = {"gap": 2, "spacing": "compact", "align": "flow"}       # djdarcy\'s pick, 2026-11-01\n',
     'DISPLAY = {"gap": 2, "spacing": "blank", "align": "blocks"}\n',
     [f"{T}::test_the_defaults_are_flow_gap_2_and_compact"]),
    ("judged counts the read twice", "ck3_save_migrator/plan.py",
     '                det.append(("judged", f"{len(t)} step(s) in {sum(t.values()):.1f} s; slowest "\n',
     '                det.append(("judged", f"{len(t)} step(s) in {sum(t.values()) + (self.detect_seconds or 0):.1f} s; slowest "\n',
     [f"{T}::test_the_detectors_block_states_the_read_and_the_judging_apart"]),
    ("field names left-aligned", "ck3_save_migrator/plan.py",
     '            name = (c.note(f"{f:>{room}}") + (": " if f else "  ")) if fw else " " * room\n',
     '            name = (c.note(f"{f:<{room}}") + (": " if f else "  ")) if fw else " " * room\n',
     [f"{T}::test_the_colons_of_a_block_line_up", f"{T}::test_status_without_a_save_prints_blocks"]),
    ("flow ignores the gap", "ck3_save_migrator/plan.py",
     "    natural = [len(h) + gap + (fw(rows) + 2 if fw(rows) else 0) for h, rows in blocks]\n",
     "    natural = [len(h) + GAP + (fw(rows) + 2 if fw(rows) else 0) for h, rows in blocks]\n",
     [f"{T}::test_under_flow_the_gap_follows_each_blocks_own_header"]),
    ("the width ignores the floor", "ck3_save_migrator/plan.py",
     "    return min(WIDTH_MAX, max(WIDTH_MIN, w or WIDTH_MAX))\n", "    return min(WIDTH_MAX, w or WIDTH_MAX)\n",
     [f"{T}::test_the_width_is_the_terminals_within_60_and_120"]),
]


def pytest(tests):
    # a fresh bytecode cache per run: a mutant the same size as the original, written within the same second,
    # would otherwise be run from the original's cached .pyc (the cache checks size and whole-second mtime) --
    # found 2026-11-01 when "gap" -> "GAP" survived for that reason alone
    import os
    import tempfile
    with tempfile.TemporaryDirectory(prefix="rg-pyc-") as pyc:
        r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *tests], cwd=ROOT,
                           capture_output=True, text=True, timeout=600,
                           env={**os.environ, "PYTHONPYCACHEPREFIX": pyc})
    return r.returncode, r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr[-300:]


def main() -> int:
    files = sorted({m[1] for m in MUTATIONS})
    backup = Path(__file__).with_suffix(".backup")
    backup.mkdir(exist_ok=True)
    original = {f: (ROOT / f).read_bytes() for f in files}
    for f in files:
        shutil.copy2(ROOT / f, backup / Path(f).name)
    bad = 0
    try:
        for name, f, old, new, tests in MUTATIONS:
            src = original[f].decode("utf-8")
            if "\r\n" in src:                                      # a CRLF checkout: match its line ends
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
    restored = all((ROOT / f).read_bytes() == (backup / Path(f).name).read_bytes() for f in files)
    print("source restored and equal to the backup:", restored)
    return 1 if bad or not restored else 0


if __name__ == "__main__":
    sys.exit(main())
