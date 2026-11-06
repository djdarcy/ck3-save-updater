"""The plan's block layout, the progress spinner, the timings and fail-early (djdarcy, 2026-11-01; the director's
three guards of 21:3x): status and update print blocks a narrow console does not tangle; --plain and NO_COLOR give
the same plain text; the spinner never writes where it should not and always erases itself; a refused plan answers
without reading the whole save, and status and update still make one plan."""

from __future__ import annotations

import io
import re
import threading

import pytest

from ck3_save_migrator import cli, detect as D
from ck3_save_migrator import plan as PL
from ck3_save_migrator import savefile as sf
from ck3_save_migrator import spinner as SP
from tests import test_update as TU
from tests.test_update import game, old_save, ref_save, run, untimed

saves = TU.saves
no_reference_from_the_environment = TU.no_reference_from_the_environment
HEADERS = ("SAVE", "GAME", "ALSO", "RECORD", "GAP", "REFERENCE", "PACKS", "PATCHES", "DETECTORS", "OUTPUT", "NOTES")


def plan_part(out: str) -> list[str]:
    """The block lines: from SAVE on, without the patches table (which keeps its own columns)."""
    lines = out.splitlines()
    lines = lines[next(n for n, ln in enumerate(lines) if ln.startswith("SAVE")):]
    i = next(n for n, ln in enumerate(lines) if ln.startswith("PATCHES"))
    j = next(n for n, ln in enumerate(lines) if n > i and ln.startswith("DETECTORS"))
    return lines[:i + 1] + lines[j:]


# --------------------------------------------------------------------------- the layout
LAYOUTS = ["", 'align = "blocks"\nspacing = "blank"\n', 'align = "global"\n']      # "": the defaults (flow)


@pytest.mark.parametrize("display", LAYOUTS)
@pytest.mark.parametrize("cols", ["60", "80", "120"])
def test_no_line_is_wider_than_the_width_and_nothing_wraps_under_a_header(tmp_path, saves, capsys, monkeypatch, cols,
                                                                          display):
    monkeypatch.setenv("COLUMNS", cols)
    write_display(display)
    code, out, err = run(capsys, "status", str(old_save(saves)), "--game-dir", str(game(tmp_path)), "--plain")
    assert code == 0
    assert [ln for ln in (out + err).splitlines() if len(ln) > int(cols)] == []
    header = None
    for ln in plan_part(out):
        if ln.startswith(HEADERS):
            header = ln.split()[0]
        elif ln:     # a continuation never starts under its block's header or the gap after it
            assert ln[:len(header) + PL.GAP].strip() == "", ln


@pytest.mark.parametrize("display", LAYOUTS)
def test_the_colons_of_a_block_line_up(tmp_path, saves, capsys, display):
    write_display(display)
    code, out, _ = run(capsys, "status", str(old_save(saves)), "--game-dir", str(game(tmp_path)), "--plain")
    block, cols = None, {}
    for ln in plan_part(out):
        if not ln:
            block = None
            continue
        if ln[:1].isupper():
            block = ln.split()[0]
        m = re.match(r"^(?:[A-Z]+)?\s+([\w-]+): ", ln)
        if block and m:
            cols.setdefault(block, set()).add(m.end() - 2)
    assert {"SAVE", "GAME", "GAP", "OUTPUT"} <= set(cols)
    assert all(len(c) == 1 for c in cols.values()), cols


def test_the_save_block_names_the_seed(tmp_path, saves, capsys):
    code, out, _ = run(capsys, "status", str(old_save(saves)), "--game-dir", str(game(tmp_path)), "--plain")
    assert re.search(r"(?m)^ +seed: 111$", out)


def test_status_without_a_save_prints_blocks(tmp_path, saves, capsys):
    old_save(saves)
    code, out, _ = run(capsys, "status", "--game-dir", str(game(tmp_path)), "--plain")
    assert code == 0 and re.search(r"(?m)^GAME +version: 1\.20\.1\.2$", out)
    assert re.search(r"(?m)^SAVES +folder: ", out) and re.search(r"(?m)^ +count: 1 save\(s\)$", out)


@pytest.mark.parametrize("cols,want", [("30", 60), ("500", 120), ("90", 90), ("", 120)])
def test_the_width_is_the_terminals_within_60_and_120(monkeypatch, cols, want):
    monkeypatch.setenv("COLUMNS", cols)
    assert PL.out_width(io.StringIO()) == want                 # a pipe (not a terminal) and no COLUMNS: 120


def test_a_long_value_wraps_under_its_own_column():
    c = PL.Paint()
    out = PL.render_blocks([("NOTES", [("", "- " + "word " * 30, None)]), ("SAVE", [("file", "x" * 90, "path")])],
                           c, 60, layout={"gap": 2, "spacing": "blank", "align": "blocks"})
    assert all(len(ln) <= 60 for ln in out)
    notes = [ln for ln in out[:out.index("")]]
    assert notes[0].startswith("NOTES  - word") and all(ln.startswith(" " * 9 + "word") for ln in notes[1:])
    assert "".join(ln.strip() for ln in out[out.index("") + 1:]).endswith("x" * 90)    # a path breaks, whole


# --------------------------------------------------------------------------- [display]: the gap and the spacing
def write_display(text: str) -> None:
    from ck3_save_migrator.config import config_path
    p = config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("[display]\n" + text, encoding="utf-8")


def test_compact_spacing_leaves_no_blank_line_and_the_same_lines_otherwise(tmp_path, saves, capsys):
    s, g = refused_setup(tmp_path, saves)
    write_display('spacing = "blank"\n')
    _, blank_out, blank_err = run(capsys, "status", str(s), "--game-dir", str(g), "--plain")
    assert "" in blank_out.splitlines() and "" in blank_err.splitlines()
    write_display('spacing = "compact"\n')
    code, out, err = run(capsys, "status", str(s), "--game-dir", str(g), "--plain")
    assert code == 1 and "" not in out.splitlines() and "" not in err.splitlines()
    drop = lambda t: [ln for ln in untimed(t).splitlines() if ln]          # noqa: E731
    assert drop(out) == drop(blank_out) and drop(err) == drop(blank_err)


@pytest.mark.parametrize("gap", [1, 2, 4])
def test_the_gap_is_the_spaces_between_the_header_column_and_the_longest_field(tmp_path, saves, capsys, gap):
    write_display(f'gap = {gap}\nalign = "blocks"\n')
    code, out, _ = run(capsys, "status", str(old_save(saves)), "--game-dir", str(game(tmp_path)), "--plain")
    head = max(len(h) for h in HEADERS if re.search(rf"(?m)^{h}\b", out))
    version = next(ln for ln in out.splitlines() if ln.startswith("GAME"))
    assert version.startswith("GAME" + " " * (head - 4 + gap) + "version: ")     # GAME's longest field
    assert re.search(r"(?m)^GAP" + " " * (head - 3 + gap) + "versions: ", out)


@pytest.mark.parametrize("gap", [1, 2, 4])
def test_under_flow_the_gap_follows_each_blocks_own_header(tmp_path, saves, capsys, gap):
    write_display(f"gap = {gap}\n")                                    # align: the default, flow
    code, out, _ = run(capsys, "status", str(old_save(saves)), "--game-dir", str(game(tmp_path)), "--plain")
    save = next(ln for ln in out.splitlines() if ln.startswith("SAVE"))
    assert save.startswith("SAVE" + " " * (gap + len("version") - len("file")) + "file: ")   # SAVE's longest: version
    assert re.search(r"(?m)^GAME" + " " * gap + "version: ", out)


@pytest.mark.parametrize("text,msg", [("gap = 0\n", "gap must be"), ("gap = 9\n", "gap must be"),
                                      ('gap = "2"\n', "gap must be"), ('spacing = "tight"\n', "spacing must be")])
def test_a_bad_display_setting_is_refused_naming_the_file(tmp_path, saves, capsys, text, msg):
    write_display(text)
    code, _, err = run(capsys, "status", str(old_save(saves)), "--game-dir", str(game(tmp_path)))
    assert code == 1 and msg in err and "config.toml" in err


# djdarcy's worked example (2026-11-01): the blocks of a refused status, with their field names
EXAMPLE = [("SAVE", ["file", "folder", "version", "format", "date", "mods", "seed"]), ("GAME", ["version", "path",
           "found"]), ("RECORD", ["status"]), ("GAP", ["versions"]), ("REFERENCE", ["status", "skips"]),
           ("PACKS", ["to_1_20"])]


def example_blocks():
    return [(h, [(f, "x", None) for f in fields]) for h, fields in EXAMPLE]


@pytest.mark.parametrize("align,want", [
    ("flow", [15, 15, 16, 16, 19, 19]),     # RECORD pushes out; GAP (one row) keeps 16; REFERENCE 19; PACKS keeps 19
    ("global", [19] * 6),                   # every block at the largest natural column (REFERENCE's)
    ("blocks", [20, 20, 19, 21, 19, 20]),   # the header column (9, REFERENCE) + the gap + each block's own fields
])
def test_the_value_columns_of_each_align(align, want):
    assert PL.value_columns(example_blocks(), {"gap": 2, "align": align}) == want


@pytest.mark.parametrize("align", ["global", "flow", "blocks"])
def test_every_row_puts_its_colon_two_before_its_blocks_value_column(align):
    layout = {"gap": 2, "align": align, "spacing": "compact"}
    out = PL.render_blocks(example_blocks(), PL.Paint(), 120, layout=layout)
    cols = PL.value_columns(example_blocks(), layout)
    rows = [c for (h, fields), c in zip(EXAMPLE, cols) for _ in fields]
    assert [ln.index(": ") + 2 for ln in out] == rows
    if align == "global":
        assert len({ln.index(": ") for ln in out}) == 1               # every colon in one column


def test_the_layout_example_in_docs_config_is_what_the_renderer_prints():
    from pathlib import Path
    doc = (Path(__file__).resolve().parents[1] / "docs" / "config.md").read_text(encoding="utf-8")
    shown = re.search(r"```\n(align = \"blocks\".*?)```", doc, re.S)[1].splitlines()
    blocks = [("SAVE", [("file", "Old.ck3", None), ("version", "1.8.1", None)]),
              ("RECORD", [("status", "none yet", None)]), ("GAP", [("versions", "1.8.1 -> ...", None)]),
              ("REFERENCE", [("status", "none chosen", None), ("skips", "R8, R10", None)]),
              ("PACKS", [("to_1_20", "selected", None)])]
    cols = [PL.render_blocks(blocks, PL.Paint(), 120, layout={"gap": 2, "spacing": "compact", "align": a})
            for a in ("blocks", "global", "flow")]
    w = [max(len(ln) for ln in c) + 3 for c in cols]
    want = ["".join(f'align = "{a}"'.ljust(x) for a, x in zip(("blocks", "global", "flow"), w)).rstrip()]
    want += ["".join(r.ljust(x) for r, x in zip(row, w)).rstrip() for row in zip(*cols)]
    assert shown == want


def test_a_bad_align_is_refused(tmp_path, saves, capsys):
    write_display('align = "left"\n')
    code, _, err = run(capsys, "status", str(old_save(saves)), "--game-dir", str(game(tmp_path)))
    assert code == 1 and "align must be one of" in err


def test_the_display_settings_survive_a_config_rewrite():
    from ck3_save_migrator import config
    write_display('gap = 3\nspacing = "compact"\n')
    config.write_disabled(["R21"])                       # disable rewrites the file with the settings it knows
    assert config.display_settings() == {"gap": 3, "spacing": "compact", "align": "flow"}
    assert config.disabled_ids() == ["R21"]


def test_the_defaults_are_flow_gap_2_and_compact(tmp_path, saves, capsys):
    """djdarcy's pick (2026-11-01); the plan's own defaults and the config's agree."""
    from ck3_save_migrator import config
    assert config.display_settings() == {"gap": 2, "spacing": "compact", "align": "flow"}
    assert (PL.GAP, PL.SPACING, PL.ALIGN) == (2, "compact", "flow")
    code, out, _ = run(capsys, "status", str(old_save(saves)), "--game-dir", str(game(tmp_path)), "--plain")
    assert "" not in out.splitlines() and re.search(r"(?m)^GAME  version: ", out)


# --------------------------------------------------------------------------- guard 1: --plain and NO_COLOR
def test_plain_and_no_color_give_the_same_text_with_no_escape_and_no_spinner(tmp_path, saves, capsys, monkeypatch):
    from ck3_save_migrator._vendor import colors
    monkeypatch.setattr(colors, "_ansi_initialized", True)
    s, g = old_save(saves), game(tmp_path)
    ref_save(saves, "A.ck3")
    ref_save(saves, "B.ck3", seed=b"random_seed=333\n")         # a refusal, so stderr has lines too
    monkeypatch.setenv("FORCE_COLOR", "1")
    code_p, out_p, err_p = run(capsys, "status", str(s), "--game-dir", str(g), "--plain")
    monkeypatch.setenv("NO_COLOR", "1")
    code_n, out_n, err_n = run(capsys, "status", str(s), "--game-dir", str(g))
    assert code_p == code_n == 1 and err_p
    assert untimed(out_p) == untimed(out_n) and err_p == err_n
    frames = {f for th in SP.SPINNERS.values() for f in th["frames"]} - set(" ")
    for text in (out_p, err_p, out_n, err_n):
        assert "\033[" not in text and "\r" not in text         # no escape, and no line redrawn in place
        assert not set(text) & frames                           # no spinner frame


# --------------------------------------------------------------------------- guard 2: the spinner
class FakeTTY(io.StringIO):
    encoding = "utf-8"

    def isatty(self):
        return True


def test_the_spinner_is_wanted_only_on_a_terminal_and_never_under_plain_quiet_json_or_no_color(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    tty = FakeTTY()
    assert SP.spinner_wanted(tty)
    assert not SP.spinner_wanted(io.StringIO())
    assert not SP.spinner_wanted(tty, plain=True)
    assert not SP.spinner_wanted(tty, quiet=1)
    assert not SP.spinner_wanted(tty, json_out=True)
    monkeypatch.setenv("NO_COLOR", "1")
    assert not SP.spinner_wanted(tty)


def test_a_disabled_spinner_writes_nothing_and_starts_no_thread():
    s = FakeTTY()
    with SP.Spinner(False, s) as sp:
        sp.update("checking R1")
    assert s.getvalue() == "" and sp._thread is None


def test_the_spinner_colours_the_frame_stage_counter_and_seconds_apart():
    """djdarcy, 2026-11-05: the frame noticeable but not the star, the stage and its counter in focus (the counter
    the same hue, brighter), the seconds receding."""
    from ck3_save_migrator._vendor import colors as C
    s = FakeTTY()
    with SP.Spinner(True, s, color=True) as sp:
        sp.update("checking R11 empty-modifiers (10 of 26)")
    drawn = s.getvalue().split("\r")[1]
    frame = next(f for f in SP.SPINNERS[SP.DEFAULT_SPINNER]["frames"] if f in drawn)
    assert drawn.startswith(C.colorize(frame, *SP.FRAME_STYLE) + " ")
    assert C.colorize("checking R11 empty-modifiers", *SP.TEXT_STYLE) in drawn
    assert C.colorize(" (10 of 26)", *SP.COUNT_STYLE) in drawn
    assert re.search(re.escape(SP.TIME_STYLE[0]) + r"  \d+ s" + re.escape(C.RESET), drawn)
    assert SP.split_counter("reading the whole save (98 MB)") == ("reading the whole save (98 MB)", "")


def test_a_spinner_without_colour_writes_no_escape():
    s = FakeTTY()
    with SP.Spinner(True, s, color=False) as sp:
        sp.update("checking R11 empty-modifiers (10 of 26)")
    assert "\033[" not in s.getvalue() and "checking R11 empty-modifiers (10 of 26)" in s.getvalue()


def test_the_spinner_draws_the_stage_and_erases_itself():
    s = FakeTTY()
    with SP.Spinner(True, s, color=False) as sp:
        sp.update("checking R23 nickname-text (3 of 12)")
    text = s.getvalue()
    assert "checking R23 nickname-text (3 of 12)" in text and text.endswith("\r")
    assert text.rsplit("\r", 2)[-2].strip() == ""                  # the last thing drawn is the blanked line
    assert not sp._thread.is_alive()


def test_the_spinner_falls_back_to_ascii_on_a_stream_that_cannot_write_its_frames():
    class Cp437(FakeTTY):
        encoding = "cp437"
    assert SP._theme(Cp437(), SP.DEFAULT_SPINNER) is SP.ASCII
    assert SP._theme(FakeTTY(), SP.DEFAULT_SPINNER)["frames"] == SP.SPINNERS[SP.DEFAULT_SPINNER]["frames"]


def test_an_error_inside_the_detectors_stops_the_spinner_and_leaves_the_line_clean(tmp_path, saves, capsys,
                                                                                    monkeypatch):
    monkeypatch.setattr(SP, "spinner_wanted", lambda *a, **k: True)
    tty = FakeTTY()
    monkeypatch.setattr(SP.sys, "stderr", tty)                  # the spinner's default stream

    def boom(g, env):
        raise RuntimeError("a detector failed")
    monkeypatch.setitem(D.DETECTORS, "R2", boom)
    with pytest.raises(RuntimeError, match="a detector failed"):
        cli.main(["status", str(old_save(saves)), "--game-dir", str(game(tmp_path))])
    text = tty.getvalue()
    assert "checking R2 relation-flags" in text and text.endswith("\r") and text.rsplit("\r", 2)[-2].strip() == ""
    assert not any(t.name == "ck3update-spinner" and t.is_alive() for t in threading.enumerate())


def test_update_names_each_stage_of_the_run_and_each_patch_as_it_runs(tmp_path, saves, capsys, monkeypatch):
    """djdarcy, 2026-11-06: after the plan, update ran its patches for two minutes with nothing on screen ("users
    will think the update has broken"). Now a spinner names reading the save, each patch with its count, the lint
    and the write, and erases itself before the output's own lines print."""
    monkeypatch.setattr(SP, "spinner_wanted", lambda *a, **k: True)
    tty = FakeTTY()
    monkeypatch.setattr(SP.sys, "stderr", tty)
    code, out, _ = run(capsys, "update", str(old_save(saves)), "--game-dir", str(game(tmp_path)), "--wos-shape",
                       "faith", "-o", str(tmp_path / "out.ck3"))
    assert code == 0
    text = re.sub(r"\x1b\[[0-9;]*m", "", tty.getvalue())                      # the line without its colours
    ran = re.findall(r"running (R\d+) [\w-]+ \((\d+) of (\d+)\)", text)
    assert ran, text[:2000]
    n = int(ran[0][2])
    assert [int(i) for _, i, _ in ran] == list(range(1, n + 1)) and n > 3
    for stage in ("reading the save", "checking the output (lint)", "writing out.ck3"):
        assert stage in text
    assert text.index("reading the save") < text.index("running R") < text.index("writing out.ck3")
    assert text.endswith("\r") and text.rsplit("\r", 2)[-2].strip() == ""      # erased, nothing left on the line
    assert "\r" not in out                                                     # stdout's lines untouched
    assert not any(t.name == "ck3update-spinner" and t.is_alive() for t in threading.enumerate())


def test_no_spinner_under_verbose_whose_timing_lines_show_each_patch(tmp_path, saves, capsys, monkeypatch):
    monkeypatch.setattr(SP, "spinner_wanted", lambda *a, **k: True)
    tty = FakeTTY()
    monkeypatch.setattr(SP.sys, "stderr", tty)
    assert cli.spin(cli.build_parser().parse_args(["update", str(old_save(saves))])).enabled is True
    assert cli.spin(cli.build_parser().parse_args(["-v", "update", str(old_save(saves))])).enabled is False


# --------------------------------------------------------------------------- progress and timing
def test_the_progress_names_each_stage_in_order_and_the_timings_cover_each_judged_step(tmp_path, saves):
    said = []
    p = PL.plan_update(old_save(saves), game_dir=str(game(tmp_path)), reference="none", detect=True,
                       progress=said.append)
    assert said[0].startswith("reading the whole save (")
    checks = [x for x in said if x.startswith("checking ")]
    n = len(checks)
    assert n == len(p.detect_timings) > 3
    assert [re.search(r"\((\d+) of (\d+)\)", x).groups() for x in checks] == [(str(i), str(n)) for i in range(1, n + 1)]
    assert [x.split()[1] for x in checks] == list(p.detect_timings)
    assert p.detect_mb and p.detect_seconds is not None and all(t >= 0 for t in p.detect_timings.values())


def test_the_detectors_block_states_the_read_and_the_judging_apart(tmp_path, saves, capsys):
    code, out, _ = run(capsys, "status", str(old_save(saves)), "--game-dir", str(game(tmp_path)), "--plain",
                       "--reference", "none")
    assert re.search(r"(?m)^READY .*  \(\d+\.\d s\)$", out)                         # the wall time, said once
    # exact numbers, so no time is counted twice: the read on its own line, the judging the sum of the steps
    p = cli.LAST_PLAN["status"]
    p.detect_seconds, p.detect_mb = 5.0, 222.3
    p.detect_timings = {"R1": 1.5, "R11": 7.0, "R2": 0.5, "R3": 1.0}
    text = "\n".join(p.lines(PL.Paint()))
    assert re.search(r"(?m)^ +read: the whole gamestate, 222\.3 MB, in 5\.0 s$", text)
    assert re.search(r"(?m)^ +judged: 4 step\(s\) in 10\.0 s; slowest R11 7\.0 s, R1 1\.5 s, R3 1\.0 s$", text)


# --------------------------------------------------------------------------- guard 3: fail early, one plan
def refused_setup(tmp_path, saves):
    s = old_save(saves)
    ref_save(saves, "A.ck3")
    ref_save(saves, "B.ck3", seed=b"random_seed=333\n")
    return s, game(tmp_path)


def test_a_refused_plan_does_not_read_the_whole_save(tmp_path, saves, capsys, monkeypatch):
    s, g = refused_setup(tmp_path, saves)
    monkeypatch.setattr(sf, "read_save", lambda *a, **k: pytest.fail("a full read of a refused plan"))
    code, out, err = run(capsys, "status", str(s), "--game-dir", str(g))
    assert code == 1 and "could each be the reference" in err
    assert re.search(r"(?m)^DETECTORS +did: not run: the plan is refused \(fail early\)", out)
    assert cli.LAST_PLAN["status"].detect_timings == {}


def test_a_refused_plan_is_the_same_plan_for_status_and_update(tmp_path, saves, capsys):
    s, g = refused_setup(tmp_path, saves)
    assert run(capsys, "status", str(s), "--game-dir", str(g))[0] == 1
    assert run(capsys, "update", str(s), "--game-dir", str(g), "--no-lint")[0] == 1
    assert cli.LAST_PLAN["update"].as_dict() == cli.LAST_PLAN["status"].as_dict()
    assert sorted(p.name for p in saves.iterdir()) == ["A.ck3", "B.ck3", "Campaign.ck3"]     # nothing written


def test_a_gap_nothing_covers_refuses_before_the_full_read(tmp_path, saves, capsys, monkeypatch):
    s = ref_save(saves, "Current.ck3", seed=b"random_seed=444\n")
    monkeypatch.setattr(sf, "read_save", lambda *a, **k: pytest.fail("a full read of a refused plan"))
    code, out, _ = run(capsys, "status", str(s), "--game-dir", str(game(tmp_path, "1.21.0")))
    assert code == 1 and "NOT COVERED: the gap 1.20.1.2 -> 1.21.0" in out
