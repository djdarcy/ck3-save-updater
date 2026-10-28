"""ck3_graphics: swap CK3 between graphics profiles (the maintainer's full-fidelity play settings, and a smaller,
lighter window for automated runs), with DLSS 5 on or off. 2026-10-28, djdarcy: "a flag to reenable full size
desktop and windowed or full-screen ... easy to swap back and forth between dev graphic settings (smaller window
lower graphic settings for your automated tests) vs restoring full graphic fidelity (potentially sans dlss5)".

What it touches, and nothing else:
  pdx_settings.txt (Documents\\Paradox Interactive\\Crusader Kings III): only the keys inside its "Graphics" section.
    The rest of the file (audio, tutorial flags, account, interface) is never rewritten, so applying a profile
    saved weeks ago does not revert anything else.
  DLSS 5 (the game's binaries folder): the two ReShade add-ons move between binaries\\ and binaries\\_dlss5_disabled\\,
    and ReShadePreset.ini becomes the DLSS 5 preset (on) or the user's own preset (off; empty when none was kept).
    The add-on install itself is described in binaries\\_dlss5_disabled\\REENABLE-DLSS5.md.

The game offers two display modes, "windowed" and "fullscreen" (OPTION_WINDOWED / OPTION_FULLSCREEN in
clausewitz/localization/cw_settings_l_english.yml; no borderless mode in the game's, Jomini's or Clausewitz's text
files). The nearest to borderless is a window at the desktop's size (--size 3840x2160).

Profiles live in private/data/graphics_profiles/<name>.json (the Graphics section's values, as written in the file).
Every apply first copies pdx_settings.txt and ReShadePreset.ini to private/data/backups/<stamp>__graphics-<name>/
with their sha256. Refuses while ck3.exe runs (the game rewrites pdx_settings.txt when it exits).

Usage:
  python -I tests/one-offs/ck3_graphics.py status
  python -I tests/one-offs/ck3_graphics.py save <name> [--from <pdx_settings.txt>]
  python -I tests/one-offs/ck3_graphics.py apply <name> [--display windowed|fullscreen] [--size WxH]
                                                        [--dlss on|off|keep] [--dry-run]
  python -I tests/one-offs/ck3_graphics.py profiles
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

GAME = Path(r"E:\SteamLibrary\steamapps\common\Crusader Kings III")
BIN = GAME / "binaries"
OFF_DIR = BIN / "_dlss5_disabled"
ADDONS = ("dlss5-feed.addon64", "renodx-dlss5-v8.5-model.addon64")
PRESET = BIN / "ReShadePreset.ini"
DLSS_PRESET = OFF_DIR / "ReShadePreset.dlss5.ini"
USER_PRESET = OFF_DIR / "ReShadePreset.user.ini"        # the user's own preset, kept while DLSS 5 is on
SETTINGS = Path(os.environ["USERPROFILE"]) / "Documents" / "Paradox Interactive" / "Crusader Kings III" / \
    "pdx_settings.txt"
PROJECT = Path(__file__).resolve().parents[2]
PROFILES = PROJECT / "private" / "data" / "graphics_profiles"
BACKUPS = PROJECT / "private" / "data" / "backups"
SHOWN = ("display_mode", "windowed_resolution", "fullscreen_resolution", "render_scale", "texture_quality",
         "shadowmap_resolution", "mesh_lod_bias", "anti_aliasing", "upscale", "vsync", "setting_framerate_cap")
KEY = re.compile(r'(\t"(\w+)"=\{\s*version=\d+\s*(?:value|enabled)=)("[^"\n]*"|[^\s}]+)')


def graphics_block(text: str) -> tuple[int, int]:
    """(start, end) of the body of the top-level "Graphics"={ ... } section."""
    m = re.search(r'(?m)^"Graphics"=\{', text)
    if not m:
        raise SystemExit("pdx_settings.txt has no \"Graphics\" section")
    depth, i = 0, m.end() - 1
    while i < len(text):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return m.end(), i
        i += 1
    raise SystemExit("pdx_settings.txt: the Graphics section is not closed")


def read_graphics(text: str) -> dict[str, str]:
    s, e = graphics_block(text)
    return {m.group(2): m.group(3) for m in KEY.finditer(text, s, e)}


def set_graphics(text: str, values: dict[str, str]) -> tuple[str, list[tuple[str, str, str]]]:
    """The file with these Graphics keys set (keys the file lacks are reported, never added)."""
    s, e = graphics_block(text)
    changes, out, last = [], [], 0
    seen = set()
    for m in KEY.finditer(text, s, e):
        k = m.group(2)
        if k in values:
            seen.add(k)
            if m.group(3) != values[k]:
                changes.append((k, m.group(3), values[k]))
                out.append(text[last:m.start(3)])
                out.append(values[k])
                last = m.end(3)
    out.append(text[last:])
    for k in sorted(set(values) - seen):
        changes.append((k, "(not in this file: left out)", values[k]))
    return "".join(out), changes


def read_text(p: Path) -> str:
    """The file's text with its line endings as written (the game writes CRLF; a normalising read would turn the
    whole file into LF on the next write: found on the first round trip, 2026-10-28)."""
    with open(p, encoding="utf-8", errors="replace", newline="") as f:
        return f.read()


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else "-"


def game_running() -> bool:
    r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq ck3.exe"], capture_output=True, text=True)
    return "ck3.exe" in r.stdout


def dlss_state() -> str:
    on = [a for a in ADDONS if (BIN / a).exists()]
    off = [a for a in ADDONS if (OFF_DIR / a).exists()]
    if len(on) == len(ADDONS) and not off:
        return "on" if sha(PRESET) == sha(DLSS_PRESET) else "on (add-ons in place, but not the DLSS 5 preset)"
    if len(off) == len(ADDONS) and not on:
        return "off"
    return f"mixed: in binaries {on}, in _dlss5_disabled {off}"


def cmd_status(_a) -> int:
    g = read_graphics(read_text(SETTINGS))
    print(f"settings : {SETTINGS}")
    for k in SHOWN:
        print(f"  {k:22} {g.get(k, '-')}")
    print(f"DLSS 5   : {dlss_state()}")
    print(f"game     : {'RUNNING (apply refuses until it exits)' if game_running() else 'not running'}")
    return 0


def cmd_profiles(_a) -> int:
    for p in sorted(PROFILES.glob("*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        g = d["graphics"]
        print(f"{p.stem:10} {g.get('display_mode', '?'):12} window {g.get('windowed_resolution', '?'):12} "
              f"fullscreen {g.get('fullscreen_resolution', '?'):12} textures {g.get('texture_quality', '?'):9} "
              f"saved {d.get('saved', '?')}  ({d.get('note', '')})")
    return 0


def cmd_save(a) -> int:
    src = Path(a.source) if a.source else SETTINGS
    g = read_graphics(read_text(src))
    PROFILES.mkdir(parents=True, exist_ok=True)
    out = PROFILES / f"{a.name}.json"
    out.write_text(json.dumps({"saved": dt.datetime.now().isoformat(timespec="seconds"), "from": str(src),
                               "note": a.note or "", "graphics": g}, indent=1), encoding="utf-8")
    print(f"saved {len(g)} Graphics settings as profile '{a.name}' -> {out}")
    return 0


def move_addons(to_on: bool, dry: bool) -> list[str]:
    done = []
    for name in ADDONS:
        src, dst = (OFF_DIR / name, BIN / name) if to_on else (BIN / name, OFF_DIR / name)
        if src.exists() and not dst.exists():
            done.append(f"move {src.name}: {src.parent.name} -> {dst.parent.name}")
            if not dry:
                os.replace(src, dst)
        elif dst.exists() and src.exists():
            raise SystemExit(f"both copies of {name} exist ({src} and {dst}); sort it out by hand first")
    return done


def cmd_apply(a) -> int:
    prof = PROFILES / f"{a.name}.json"
    if not prof.exists():
        raise SystemExit(f"no profile '{a.name}' ({prof}); `profiles` lists them, `save` makes one")
    if game_running() and not a.dry_run:
        raise SystemExit("ck3.exe is running: it rewrites pdx_settings.txt when it exits, so the change would be lost")
    want = dict(json.loads(prof.read_text(encoding="utf-8"))["graphics"])
    if a.display:
        want["display_mode"] = f'"{a.display}"'
    if a.size:
        if not re.fullmatch(r"\d{3,5}x\d{3,5}", a.size):
            raise SystemExit(f"--size must be WIDTHxHEIGHT, e.g. 2560x1440 (got {a.size})")
        mode = (a.display or want.get("display_mode", '"windowed"').strip('"'))
        want["fullscreen_resolution" if mode == "fullscreen" else "windowed_resolution"] = f'"{a.size}"'
    text = read_text(SETTINGS)
    new, changes = set_graphics(text, want)
    plan = [f"{k}: {old} -> {v}" for k, old, v in changes]
    dl = []
    if a.dlss in ("on", "off"):
        if dlss_state().startswith("mixed"):
            raise SystemExit(f"DLSS 5 is in a mixed state ({dlss_state()}); fix it by hand first")
        dl = move_addons(a.dlss == "on", dry=True)
        if a.dlss == "on" and sha(PRESET) != sha(DLSS_PRESET):
            dl.append("ReShadePreset.ini: keep the current one as _dlss5_disabled/ReShadePreset.user.ini; "
                      "use the DLSS 5 preset")
        if a.dlss == "off" and sha(PRESET) == sha(DLSS_PRESET):
            dl.append("ReShadePreset.ini: back to " + ("ReShadePreset.user.ini" if USER_PRESET.exists() else "empty"))
    print(f"profile '{a.name}'{' (dry run: nothing written)' if a.dry_run else ''}")
    for line in plan or ["Graphics: already as the profile says"]:
        print("  " + line)
    for line in dl or [f"DLSS 5: {'unchanged' if a.dlss == 'keep' else 'already ' + a.dlss} ({dlss_state()})"]:
        print("  " + line)
    if a.dry_run or (not changes and not dl):
        return 0
    stamp = dt.datetime.now().strftime("%Y-%m-%d__%H-%M-%S")
    bk = BACKUPS / f"{stamp}__graphics-{a.name}"
    bk.mkdir(parents=True)
    hashes = {}
    for p in (SETTINGS, PRESET):
        if p.exists():
            shutil.copy2(p, bk / p.name)
            hashes[p.name] = sha(p)
    (bk / "sha256.json").write_text(json.dumps(hashes, indent=1), encoding="utf-8")
    if changes:
        tmp = SETTINGS.with_name(SETTINGS.name + ".tmp")
        tmp.write_text(new, encoding="utf-8", newline="")
        os.replace(tmp, SETTINGS)
    if a.dlss == "on":
        move_addons(True, dry=False)
        if sha(PRESET) != sha(DLSS_PRESET):
            shutil.copy2(PRESET, USER_PRESET)
            shutil.copy2(DLSS_PRESET, PRESET)
    elif a.dlss == "off":
        move_addons(False, dry=False)
        if sha(PRESET) == sha(DLSS_PRESET):
            if USER_PRESET.exists():
                shutil.copy2(USER_PRESET, PRESET)
            else:
                PRESET.write_bytes(b"")
    after = read_graphics(read_text(SETTINGS))
    bad = [k for k, v in want.items() if k in after and after[k] != v]
    print(f"backup  : {bk}")
    print(f"result  : {'Graphics as the profile says' if not bad else 'NOT applied: ' + str(bad)}; DLSS 5 {dlss_state()}")
    return 1 if bad else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Swap CK3 graphics profiles and DLSS 5 (see the module docstring).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    sub.add_parser("profiles").set_defaults(fn=cmd_profiles)
    s = sub.add_parser("save")
    s.add_argument("name")
    s.add_argument("--from", dest="source", help="read another pdx_settings.txt (a backup) instead of the live one")
    s.add_argument("--note", help="a line saying what the profile is for")
    s.set_defaults(fn=cmd_save)
    p = sub.add_parser("apply")
    p.add_argument("name")
    p.add_argument("--display", choices=("windowed", "fullscreen"))
    p.add_argument("--size", help="WIDTHxHEIGHT for the chosen display mode (a desktop-sized window ~ borderless)")
    p.add_argument("--dlss", choices=("on", "off", "keep"), default="keep")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(fn=cmd_apply)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
