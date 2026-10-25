"""Launch CK3 directly (no launcher) with given args, watch its logs, screenshot, collect evidence.

Usage:
  python -I launch_load_test.py <run-name> [extra ck3 args...]
Example:
  python -I launch_load_test.py baseline-orig-1.8.1 -debug_mode "-loadsave=MIGRATE_TEST__Beidh_987_10_27__orig_1.8.1.ck3"

Writes everything to <project>/private/data/runs/<timestamp>__<run-name>/:
  cmdline.txt, timeline.txt (what we saw when), shots/*.png (periodic screen captures),
  logs/ (copy of the game's logs folder at the end), crashes/ (any new crash folders).
Stops when the process exits, when a crash dump appears, after MAX_SECONDS, or when
the user creates the file STOP in the run folder. Never touches the save files.
"""
import datetime as dt
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

GAME = Path(r"E:\SteamLibrary\steamapps\common\Crusader Kings III")
EXE = GAME / "binaries" / "ck3.exe"
DOCS = Path(os.environ["USERPROFILE"]) / "Documents" / "Paradox Interactive" / "Crusader Kings III"
LOGS = DOCS / "logs"
CRASHES = DOCS / "crashes"
PROJECT = Path(r"C:\code\ck3-save-migrator")
SHOT = Path(os.environ["USERPROFILE"]) / ".claude" / "skills" / "screenshot" / "shot.ps1"
MAX_SECONDS = 15 * 60
SHOT_EVERY = 20
POLL = 2

# log lines worth timestamping as they appear
WATCH = [
    (re.compile(r"Could not load save game"), "LOAD-FAILED"),
    (re.compile(r"jomini_savegame_load_failed"), "LOAD-FAILED"),
    (re.compile(r"Total startup duration"), "FRONTEND-READY"),
    (re.compile(r"Setting idler '([^']+)'"), "IDLER"),
    (re.compile(r"\[E\]"), "ERROR"),
    (re.compile(r"Loading save|LoadSave|load save|savegame", re.I), "SAVE"),
    (re.compile(r"version", re.I), "VERSION"),
    (re.compile(r"crash|exception|assert", re.I), "CRASH?"),
]


def find_main_window(pid: int) -> int:
    """Top-level visible window owned by pid, or 0."""
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    result = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def cb(h, _):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(h, ctypes.byref(owner))
        if owner.value == pid and user32.IsWindowVisible(h) and user32.GetWindow(h, 4) == 0:  # GW_OWNER
            result.append(h)
        return True

    user32.EnumWindows(cb, 0)
    return result[0] if result else 0


def send_to_back(hwnd: int) -> None:
    """Z-order the window to the bottom without activating it (user keeps working on top)."""
    import ctypes
    HWND_BOTTOM, SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE = 1, 0x0001, 0x0002, 0x0010
    ctypes.windll.user32.SetWindowPos(hwnd, HWND_BOTTOM, 0, 0, 0, 0, SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE)


def tail_new(path: Path, pos: dict) -> list[str]:
    if not path.exists():
        return []
    size = path.stat().st_size
    last = pos.get(path, 0)
    if size < last:
        last = 0  # file was rotated/truncated
    if size == last:
        return []
    with path.open("rb") as f:
        f.seek(last)
        data = f.read(size - last)
    pos[path] = size
    return data.decode("utf-8", errors="replace").splitlines()


def main(run_name: str, args: list[str]) -> int:
    # game logs carry names like "Bolesław"; a cp1252 console would kill the watcher mid-run
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    stamp = dt.datetime.now().strftime("%Y-%m-%d__%H-%M-%S")
    run = PROJECT / "private" / "data" / "runs" / f"{stamp}__{run_name}"
    (run / "shots").mkdir(parents=True)
    cmd = [str(EXE), "-gdpr-compliant", *args]
    (run / "cmdline.txt").write_text(" ".join(cmd) + "\n", encoding="utf-8")
    timeline = (run / "timeline.txt").open("a", encoding="utf-8")

    def note(msg: str) -> None:
        line = f"[{dt.datetime.now():%H:%M:%S}] {msg}"
        print(line, flush=True)
        timeline.write(line + "\n")
        timeline.flush()

    crashes_before = {p.name for p in CRASHES.iterdir()} if CRASHES.exists() else set()
    # a wedged GPU driver makes ck3.exe die at "Failed creating DX11 device" before touching any save
    probe = subprocess.run([sys.executable, "-I", str(Path(__file__).with_name("d3d11_probe.py"))],
                           capture_output=True, text=True)
    note("d3d11 probe: " + probe.stdout.strip().replace("\n", " | "))
    if probe.returncode != 0:
        note("abort: hardware DX11 device creation fails system-wide; restart the graphics driver or reboot first")
        timeline.close()
        return 3
    note(f"launch: {' '.join(cmd)}")
    proc = subprocess.Popen(cmd, cwd=str(EXE.parent))
    note(f"pid {proc.pid}")

    # start past whatever a previous run left in the logs; the game truncates them on start,
    # and tail_new resets to 0 when a file shrinks
    pos: dict = {LOGS / n: (LOGS / n).stat().st_size for n in
                 ("debug.log", "error.log", "game.log", "system.log", "setup.log") if (LOGS / n).exists()}
    t0 = time.time()
    last_shot = 0.0
    shot_n = 0
    error_lines = 0
    rc = None
    stop_reason = "timeout"
    hwnd = 0
    pushed_back_until = t0 + 90   # the game raises its window more than once while loading
    try:
        while True:
            elapsed = time.time() - t0
            rc = proc.poll()
            if rc is not None:
                stop_reason = f"process exited rc={rc}"
                break
            # keep the game window behind the user's work (windowed mode is set in pdx_settings.txt)
            if not hwnd or time.time() < pushed_back_until:
                found = find_main_window(proc.pid)
                if found and found != hwnd:
                    hwnd = found
                    note(f"window hwnd=0x{hwnd:x}")
                if hwnd:
                    send_to_back(hwnd)
            if (run / "STOP").exists():
                stop_reason = "STOP file"
                if "kill" in (run / "STOP").read_text(errors="ignore").lower():
                    proc.terminate()   # STOP containing "kill" also closes the game
                    stop_reason = "STOP file (killed game)"
                break
            if elapsed > MAX_SECONDS:
                break
            for name in ("debug.log", "error.log", "game.log", "system.log", "setup.log"):
                for line in tail_new(LOGS / name, pos):
                    tags = [tag for rx, tag in WATCH if rx.search(line)]
                    if name == "error.log":
                        error_lines += 1
                        if error_lines <= 60:
                            note(f"error.log: {line[:300]}")
                    elif tags and tags != ["VERSION"]:
                        note(f"{name} {'/'.join(dict.fromkeys(tags))}: {line[:300]}")
            if CRASHES.exists():
                new = {p.name for p in CRASHES.iterdir()} - crashes_before
                if new:
                    note(f"CRASH folder appeared: {sorted(new)}")
                    stop_reason = "crash dump"
                    time.sleep(10)
                    break
            # the game window only, never the screen: until the window exists there is no shot. (The old
            # fallback to -Screen captured the whole desktop as each run's first image; 2026-10-25.)
            if hwnd and time.time() - last_shot >= SHOT_EVERY:
                shot_n += 1
                out = run / "shots" / f"{shot_n:03d}__{int(elapsed):04d}s.png"
                try:
                    target = ["-Hwnd", f"0x{hwnd:x}"]
                    r = subprocess.run(["pwsh", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                                        "-File", str(SHOT), *target, "-Out", str(out)],
                                       capture_output=True, text=True, timeout=30, stdin=subprocess.DEVNULL)
                    if not out.exists():
                        note(f"shot failed: {(r.stdout + r.stderr).strip()[:300]}")
                except subprocess.TimeoutExpired:
                    note("shot failed: shot.ps1 timed out after 30s")
                last_shot = time.time()
            time.sleep(POLL)
    finally:
        note(f"stop: {stop_reason} after {int(time.time() - t0)}s; error.log lines seen: {error_lines}")
        if LOGS.exists():
            shutil.copytree(LOGS, run / "logs", dirs_exist_ok=True)
        if CRASHES.exists():
            for p in CRASHES.iterdir():
                if p.name not in crashes_before:
                    shutil.copytree(p, run / "crashes" / p.name, dirs_exist_ok=True)
        timeline.close()
        print(f"run folder: {run}")
    return 0 if rc in (None, 0) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2:]))
