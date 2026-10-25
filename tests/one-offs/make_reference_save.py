"""Start a fresh CK3 game from a bookmark and write a reference save through the debug console.

Why: a save written by the installed game (1.20.1.2) is the schema reference every patch rule is
measured against (which keys exist, bitset widths, DNA length, save_game_version...).

Usage: python -I make_reference_save.py <save-name> [bookmark] [history_id]
Default bookmark bm_867_persia / character 163101 (the first entry in game/common/bookmarks).

Flow: launch ck3.exe -debug_mode -bookmark=<bm> -play=<id> (the game_setup.cpp launch options),
wait until the in-game session is up (debug.log), briefly focus the window, open the console (`),
type `save_text <name>`, close the console, wait for the file to appear in save games/, then quit.
The window is sent back behind the user's work between keystroke bursts. Writes nothing but the
new save file and a run folder under private/data/runs/.
"""
import datetime as dt
import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from launch_load_test import DOCS, EXE, LOGS, PROJECT, SHOT, find_main_window, send_to_back, tail_new  # noqa: E402

SAVES = DOCS / "save games"


def focus(hwnd: int) -> None:
    import ctypes
    user32 = ctypes.windll.user32
    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.6)


def type_console(hwnd: int, command: str, note) -> None:
    import pyautogui
    pyautogui.FAILSAFE = False
    focus(hwnd)
    pyautogui.press("`")           # open console (debug mode)
    time.sleep(0.8)
    pyautogui.typewrite(command, interval=0.03)
    time.sleep(0.3)
    pyautogui.press("enter")
    time.sleep(1.0)
    pyautogui.press("`")           # close console
    time.sleep(0.5)
    send_to_back(hwnd)
    note(f"typed console command: {command}")


def shot(hwnd: int, out: Path) -> None:
    subprocess.run(["pwsh", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(SHOT),
                    "-Hwnd", f"0x{hwnd:x}", "-Out", str(out)], capture_output=True, text=True, timeout=30,
                   stdin=subprocess.DEVNULL)


def main(name: str, bookmark: str, history_id: str) -> int:
    stamp = dt.datetime.now().strftime("%Y-%m-%d__%H-%M-%S")
    run = PROJECT / "private" / "data" / "runs" / f"{stamp}__reference-save-{name}"
    (run / "shots").mkdir(parents=True)
    timeline = (run / "timeline.txt").open("a", encoding="utf-8")

    def note(msg: str) -> None:
        line = f"[{dt.datetime.now():%H:%M:%S}] {msg}"
        print(line, flush=True)
        timeline.write(line + "\n")
        timeline.flush()

    target = SAVES / f"{name}.ck3"
    if target.exists():
        note(f"abort: {target} already exists")
        return 2
    cmd = [str(EXE), "-gdpr-compliant", "-debug_mode", f"-bookmark={bookmark}", f"-play={history_id}"]
    note("launch: " + " ".join(cmd))
    proc = subprocess.Popen(cmd, cwd=str(EXE.parent))
    pos = {LOGS / n: (LOGS / n).stat().st_size for n in ("debug.log", "error.log", "game.log") if (LOGS / n).exists()}
    hwnd = 0
    t0 = time.time()
    in_game_since = 0.0
    typed = False
    shots = 0
    try:
        while time.time() - t0 < 600:
            if proc.poll() is not None:
                note(f"process exited rc={proc.returncode}")
                break
            if not hwnd:
                hwnd = find_main_window(proc.pid)
                if hwnd:
                    note(f"window hwnd=0x{hwnd:x}")
            if hwnd and not typed:
                send_to_back(hwnd)
            for line in tail_new(LOGS / "debug.log", pos):
                if re.search(r"Setting idler|idlerlogic|Total startup duration|bookmark|Bookmark", line):
                    note("debug.log: " + line[:220])
                if re.search(r"Setting idler 'In ?Game'|ingameidlerlogic", line, re.I) and not in_game_since:
                    in_game_since = time.time()
                    note("in-game idler detected")
            for line in tail_new(LOGS / "game.log", pos):
                note("game.log: " + line[:220])
            if hwnd and in_game_since and not typed and time.time() - in_game_since > 25:
                shot(hwnd, run / "shots" / f"before-console-{int(time.time()-t0)}s.png")
                type_console(hwnd, f"save_text {name}", note)
                typed = True
                shot(hwnd, run / "shots" / f"after-console-{int(time.time()-t0)}s.png")
            if typed and target.exists() and target.stat().st_size > 1_000_000:
                time.sleep(5)
                note(f"save written: {target} ({target.stat().st_size:,} bytes)")
                shot(hwnd, run / "shots" / f"after-save-{int(time.time()-t0)}s.png")
                break
            if hwnd and int(time.time() - t0) % 30 == 0 and shots < 20:
                shots += 1
                shot(hwnd, run / "shots" / f"{shots:03d}__{int(time.time()-t0):04d}s.png")
                time.sleep(1)
            time.sleep(2)
    finally:
        if proc.poll() is None:
            note("terminating game")
            proc.terminate()
        timeline.close()
        print(f"run folder: {run}")
    return 0 if target.exists() else 1


if __name__ == "__main__":
    args = sys.argv[1:]
    sys.exit(main(args[0], args[1] if len(args) > 1 else "bm_867_persia", args[2] if len(args) > 2 else "163101"))
