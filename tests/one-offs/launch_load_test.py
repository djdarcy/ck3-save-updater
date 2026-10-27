"""Launch CK3 directly (no launcher) with given args, watch its logs, screenshot, collect evidence.

Usage:
  python -I launch_load_test.py <run-name> [extra ck3 args...]
Example:
  python -I launch_load_test.py baseline-orig-1.8.1 -debug_mode "-loadsave=MIGRATE_TEST__Beidh_987_10_27__orig_1.8.1.ck3"

Writes everything to <project>/private/data/runs/<timestamp>__<run-name>/:
  cmdline.txt, timeline.txt (what we saw when), shots/*.webp (periodic screen captures, WebP quality 90),
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
# a bare "bash" from Python can resolve to WSL's (System32\bash.exe), which cannot run our scripts: name Git Bash
GIT_BASH = next((p for p in (r"C:\Program Files\Git\bin\bash.exe", r"C:\Program Files\Git\usr\bin\bash.exe")
                 if Path(p).exists()), "bash")
TMP_SHOT = Path(os.environ.get("TEMP", str(Path.home()))) / "ck3_launch_last_shot.png"   # overwritten each shot
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


def post_console(hwnd: int, command: str) -> None:
    """Type a console command into the game window by POSTED messages (no focus taken): the console key (`),
    the command's characters, Enter, and the console key again to close it. Needs -debug_mode."""
    import ctypes
    import time as _t
    user32 = ctypes.windll.user32
    WM_KEYDOWN, WM_KEYUP, WM_CHAR = 0x0100, 0x0101, 0x0102
    VK_OEM_3, VK_RETURN = 0xC0, 0x0D

    def key(vk: int, ch: str | None = None) -> None:
        scan = user32.MapVirtualKeyW(vk, 0)
        user32.PostMessageW(hwnd, WM_KEYDOWN, vk, 1 | (scan << 16))
        if ch is not None:
            user32.PostMessageW(hwnd, WM_CHAR, ord(ch), 1 | (scan << 16))
        user32.PostMessageW(hwnd, WM_KEYUP, vk, 1 | (scan << 16) | (0xC0 << 24))
        _t.sleep(0.05)

    key(VK_OEM_3)
    _t.sleep(0.5)
    for ch in command:
        user32.PostMessageW(hwnd, WM_CHAR, ord(ch), 1)
        _t.sleep(0.02)
    key(VK_RETURN, "\r")
    _t.sleep(0.5)
    key(VK_OEM_3)


KEYS = {"space": 0x20, "plus": 0x6B, "minus": 0x6D, "1": 0x31, "2": 0x32, "3": 0x33, "4": 0x34, "5": 0x35,
        "enter": 0x0D, "escape": 0x1B}


def post_key(hwnd: int, name: str) -> None:
    """One key press (down, char where printable, up) posted to the game window; no focus taken."""
    import ctypes
    import time as _t
    user32 = ctypes.windll.user32
    vk = KEYS[name]
    scan = user32.MapVirtualKeyW(vk, 0)
    user32.PostMessageW(hwnd, 0x0100, vk, 1 | (scan << 16))
    if name in ("space", "1", "2", "3", "4", "5"):
        user32.PostMessageW(hwnd, 0x0102, ord(" " if name == "space" else name), 1 | (scan << 16))
    user32.PostMessageW(hwnd, 0x0101, vk, 1 | (scan << 16) | (0xC0 << 24))
    _t.sleep(0.3)


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
    # harness options (not passed to the game): --h-console=CMD types CMD into the debug console once, a few
    # seconds after the 'In Game' idler; repeatable, sent in order
    consoles = [a.split("=", 1)[1] for a in args if a.startswith("--h-console=")]
    # --h-key=NAME: keys posted once, in order, after the console commands (space, plus, 1-5, ...)
    keys = [a.split("=", 1)[1] for a in args if a.startswith("--h-key=")]
    # --h-max=SECONDS: run length cap (default 15 min); --h-guard-autosave: back up the user's autosave*.ck3 first
    # and restore any that changed when the run ends (a long run writes the yearly autosave)
    global MAX_SECONDS
    MAX_SECONDS = next((int(a.split("=", 1)[1]) for a in args if a.startswith("--h-max=")), MAX_SECONDS)
    guard = "--h-guard-autosave" in args
    # --h-keepalive: after the keys are sent, compare the date area of each shot with the previous one; the date
    # moves several times a second at speed, so an unchanged date means the game paused itself (on a message or
    # an event, as the 2026-10-26 soaks found) and one space is posted to unpause it. Every press is noted, so a
    # run that keeps pressing has hung rather than paused.
    keepalive = "--h-keepalive" in args
    last_date_sig = None
    stuck_presses = 0        # consecutive keepalive presses that did not move the date
    args = [a for a in args if not a.startswith("--h-")]
    keys_sent = False
    in_game_at = None
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
    saves_dir = DOCS / "save games"
    guarded: dict[str, str] = {}
    if guard:
        import hashlib
        (run / "autosave-guard").mkdir()
        for f in saves_dir.glob("autosave*.ck3"):
            shutil.copy2(f, run / "autosave-guard" / f.name)
            guarded[f.name] = hashlib.sha256(f.read_bytes()).hexdigest()
        note(f"autosave guard: {len(guarded)} file(s) copied and hashed")
    # a wedged GPU driver makes ck3.exe die at "Failed creating DX11 device" before touching any save
    probe = subprocess.run([sys.executable, "-I", str(Path(__file__).with_name("d3d11_probe.py"))],
                           capture_output=True, text=True)
    note("d3d11 probe: " + probe.stdout.strip().replace("\n", " | "))
    if probe.returncode != 0:
        note("abort: hardware DX11 device creation fails system-wide; restart the graphics driver or reboot first")
        timeline.close()
        return 3
    # injected DLLs the game loads from its own folder (ReShade is dxgi.dll): recorded per run for crash triage
    for dll in ("dxgi.dll", "d3d11.dll", "dinput8.dll"):
        p = EXE.parent / dll
        if p.exists():
            st = p.stat()
            note(f"injected dll present: {dll} {st.st_size} bytes, modified "
                 f"{time.strftime('%Y-%m-%d %H:%M', time.localtime(st.st_mtime))}")
        else:
            note(f"injected dll absent: {dll}")
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
                        if "Setting idler 'In Game'" in line and in_game_at is None:
                            in_game_at = time.time()
            if consoles and in_game_at and hwnd and time.time() - in_game_at > 8:
                cmd_txt = consoles.pop(0)
                note(f"console (posted, no focus): {cmd_txt}")
                post_console(hwnd, cmd_txt)
                in_game_at = time.time()          # the next command waits another 8 s
            elif keys and not consoles and not keys_sent and in_game_at and hwnd and time.time() - in_game_at > 8:
                for k in keys:
                    post_key(hwnd, k)
                note(f"keys (posted, no focus): {' '.join(keys)}")
                keys_sent = True
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
                # shot.ps1 writes PNG; it goes to one temp file overwritten every shot, and the run keeps a WebP
                # (quality 90: about 7% of the PNG's size, 2026-10-27, djdarcy: the PNGs were eating the disk)
                tmp_png = TMP_SHOT
                out = run / "shots" / f"{shot_n:03d}__{int(elapsed):04d}s.webp"
                try:
                    target = ["-Hwnd", f"0x{hwnd:x}"]
                    if tmp_png.exists():
                        tmp_png.unlink()                 # our own scratch file from the previous shot
                    r = subprocess.run(["pwsh", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                                        "-File", str(SHOT), *target, "-Out", str(tmp_png)],
                                       capture_output=True, text=True, timeout=30, stdin=subprocess.DEVNULL)
                    if not tmp_png.exists():
                        note(f"shot failed: {(r.stdout + r.stderr).strip()[:300]}")
                    else:
                        from PIL import Image, ImageChops, ImageStat
                        im = Image.open(tmp_png).convert("RGB")
                        im.save(out, "WEBP", quality=90, method=4)
                        if keepalive and keys_sent:
                            # the date text only (not the speed icon or the animated bar beside it), compared with
                            # a tolerance: exact bytes never matched because of small animations
                            w, h = im.size
                            date = im.crop((int(w * 0.65), int(h * 0.94), int(w * 0.83), int(h * 0.985))).convert("L")
                            if last_date_sig is not None and last_date_sig.size == date.size and \
                                    ImageStat.Stat(ImageChops.difference(date, last_date_sig)).mean[0] < 2.0:
                                stuck_presses += 1
                                if stuck_presses == 3:
                                    # three presses changed nothing: a frozen simulation, not a pause; record it
                                    cap = subprocess.run([GIT_BASH, str(Path(__file__).with_name("ck3_freeze_capture.sh")),
                                                          str(run / f"freeze_{shot_n:03d}")],
                                                         capture_output=True, text=True, timeout=180)
                                    note("freeze capture: " + cap.stdout.strip().replace("\n", " | ")[:400])
                                post_key(hwnd, "space")
                                note("keepalive: the date did not move since the last shot; space posted")
                            else:
                                stuck_presses = 0
                            last_date_sig = date
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
        if guard:
            import hashlib
            proc.poll() is None and proc.terminate()      # the game must be gone before its files are put back
            time.sleep(3)
            for f in saves_dir.glob("autosave*.ck3"):
                h = hashlib.sha256(f.read_bytes()).hexdigest()
                if f.name not in guarded:
                    shutil.move(str(f), str(run / f.name))              # new: the soak's own save, kept as evidence
                    note(f"autosave guard: new {f.name} moved to the run folder")
                elif h != guarded[f.name]:
                    shutil.copy2(f, run / f"soak__{f.name}")            # keep the game's version too
                    shutil.copy2(run / "autosave-guard" / f.name, f)    # and restore the user's
                    note(f"autosave guard: {f.name} changed; the game's copy kept as soak__{f.name}, the user's restored")
            for name, h in guarded.items():
                cur = saves_dir / name
                ok = cur.exists() and hashlib.sha256(cur.read_bytes()).hexdigest() == h
                note(f"autosave guard: {name} {'verified' if ok else 'NOT VERIFIED -- restore from ' + str(run / 'autosave-guard')}")
        timeline.close()
        print(f"run folder: {run}")
    return 0 if rc in (None, 0) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2:]))
