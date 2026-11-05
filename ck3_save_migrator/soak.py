"""``soak``: load a save in the game, let it run, close it through the game's own Exit to Desktop, and say how it
ended. This STARTS CRUSADER KINGS III.

Built from the project's harness ``tests/one-offs/launch_load_test.py`` (left as it is): the window functions, the
key table, the Exit to Desktop point and the log tail are copied from it unchanged; the run loop is the harness's,
trimmed to what this command does. The ``dlc_load.json`` handling follows ``tests/one-offs/with_portrait_mods.py``.

What it does, in order:

1. refuses when another soak holds the lock, or when the game is already running;
2. backs up the player's ``autosave*.ck3`` (with their sha256) and ``dlc_load.json`` into the run folder;
3. with ``--mods``, enables exactly those mods in ``dlc_load.json`` for the run;
4. copies the save into the game's save folder as ``MIGRATE_TEST__<name>.ck3``;
5. starts the game with ``-debug_mode -loadsave=MIGRATE_TEST__<name>.ck3``, watches its logs, and once it is in game
   presses space (unpause) and the speed key; while it runs, a date that stops moving gets one space press;
6. after ``--exit-after`` seconds in game (``--minutes`` x 60), closes the window (WM_CLOSE opens the Exit Game
   dialog) and clicks Exit to Desktop, DPI-aware;
7. whatever happened: stops the game if it still runs, puts back every autosave the game changed and moves the
   ones it made into the run folder (each check reported), removes the staged save if it was put there by this run,
   restores ``dlc_load.json`` byte for byte and checks it, and releases the lock.

Nothing else is written into the player's folders. The run folder (backups, the timeline, copies of the game's
logs and of any crash folder) is in the tool's cache folder unless ``--run-dir`` says otherwise.

Outcomes: ``clean exit``, ``crash on exit`` (with the first line of the crash folder's ``exception.txt``),
``crash while running``, ``did not load``, ``did not exit``.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

STAGED_PREFIX = "MIGRATE_TEST__"
LOAD_TIMEOUT = 15 * 60          # seconds to reach 'In Game' before the run is called "did not load"
KEYS_DELAY = 8                  # seconds after 'In Game' before the keys (the harness's wait)
EXIT_WAIT = 120                 # seconds after WM_CLOSE before the run is called "did not exit"
CRASH_WAIT = 30                 # seconds to wait for a crash folder after the process ends
POLL = 2
LOGS = ("debug.log", "error.log", "game.log", "system.log", "setup.log")

# log lines worth timestamping as they appear (from the harness)
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


# --------------------------------------------------------------------------- copied from the harness unchanged
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


KEYS = {"space": 0x20, "plus": 0x6B, "minus": 0x6D, "1": 0x31, "2": 0x32, "3": 0x33, "4": 0x34, "5": 0x35,
        "enter": 0x0D, "escape": 0x1B, "f1": 0x70, "f8": 0x77}   # F1 the character window, F8 culture (2026-11-04)


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


def click_client(hwnd: int, fx: float, fy: float, real: bool = False) -> str:
    """Click at a fraction (fx, fy) of the window's client area. By posted messages (no focus taken), or with
    real=True by moving the cursor there and sending a real click (takes focus: only when the machine is ours)."""
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    rc = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(rc))
    x, y = int(rc.right * fx), int(rc.bottom * fy)
    if not real:
        lp = (y << 16) | (x & 0xFFFF)
        for msg, wp in ((0x0200, 0), (0x0201, 1), (0x0202, 0)):       # WM_MOUSEMOVE, LBUTTONDOWN, LBUTTONUP
            user32.PostMessageW(hwnd, msg, wp, lp)
            time.sleep(0.1)
        return f"posted click at client ({x},{y}) of {rc.right}x{rc.bottom}"
    pt = wintypes.POINT(x, y)
    user32.ClientToScreen(hwnd, ctypes.byref(pt))
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.5)
    user32.SetCursorPos(pt.x, pt.y)
    time.sleep(0.3)
    user32.mouse_event(0x0002, 0, 0, 0, 0)                           # MOUSEEVENTF_LEFTDOWN
    time.sleep(0.1)
    user32.mouse_event(0x0004, 0, 0, 0, 0)                           # MOUSEEVENTF_LEFTUP
    return f"real click at screen ({pt.x},{pt.y})"


# "Exit to Desktop" in the Exit Game dialog that WM_CLOSE opens, as a fraction of the client area (measured on
# a 3862x2216 window shot, 2026-10-27: the button's centre at 1930,1270 with a 44 px title bar)
EXIT_TO_DESKTOP = (0.4997, 0.5645)


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


# --------------------------------------------------------------------------- small Windows helpers of this command
def dpi_aware() -> None:
    """See the game's real pixels (the harness's line): without it, display scaling reports a 3860x2170 client area
    as 2560x1440 and the Exit to Desktop click lands short."""
    import ctypes
    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))   # PER_MONITOR_AWARE_V2


def post_close(hwnd: int) -> None:
    """WM_CLOSE, as Alt+F4: the game opens its Exit Game dialog and, from there, runs its own shutdown."""
    import ctypes
    ctypes.windll.user32.PostMessageW(hwnd, 0x0010, 0, 0)


def date_signature(hwnd: int) -> bytes | None:
    """The pixels of the date text (the harness's crop: 65-83% across, 94-98.5% down the client area), grey, from
    the window itself through GDI; None when it cannot be read. Two signatures are compared to tell a running game
    from a paused one."""
    import ctypes
    from ctypes import wintypes
    user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
    rc = wintypes.RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(rc)) or rc.right <= 0 or rc.bottom <= 0:
        return None
    x0, y0 = int(rc.right * 0.65), int(rc.bottom * 0.94)
    w, h = max(1, int(rc.right * 0.83) - x0), max(1, int(rc.bottom * 0.985) - y0)
    src = user32.GetDC(hwnd)
    mem = gdi32.CreateCompatibleDC(src)
    bmp = gdi32.CreateCompatibleBitmap(src, w, h)
    try:
        gdi32.SelectObject(mem, bmp)
        gdi32.BitBlt(mem, 0, 0, w, h, src, x0, y0, 0x00CC0020)     # SRCCOPY

        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [("biSize", wintypes.DWORD), ("biWidth", ctypes.c_long), ("biHeight", ctypes.c_long),
                        ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD),
                        ("biCompression", wintypes.DWORD), ("biSizeImage", wintypes.DWORD),
                        ("biXPelsPerMeter", ctypes.c_long), ("biYPelsPerMeter", ctypes.c_long),
                        ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]
        bih = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
        buf = ctypes.create_string_buffer(w * h * 4)
        if not gdi32.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(bih), 0):
            return None
        raw = buf.raw
        return bytes((raw[i] + raw[i + 1] + raw[i + 2]) // 3 for i in range(0, len(raw), 4))
    finally:
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(mem)
        user32.ReleaseDC(hwnd, src)


def same_date(a: bytes | None, b: bytes | None) -> bool:
    """Two date signatures alike within the harness's tolerance (mean difference under 2 of 255)."""
    if a is None or b is None or len(a) != len(b) or not a:
        return False
    return sum(abs(x - y) for x, y in zip(a, b)) / len(a) < 2.0


def game_running() -> bool:
    """Whether a CK3 process is running."""
    try:
        import psutil
        return any((p.info.get("name") or "").lower() in ("ck3.exe", "ck3") for p in psutil.process_iter(["name"]))
    except ImportError:
        pass
    if sys.platform == "win32":
        r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq ck3.exe", "/NH"], capture_output=True, text=True)
        return "ck3.exe" in r.stdout.lower()
    r = subprocess.run(["pgrep", "-x", "ck3"], capture_output=True)
    return r.returncode == 0


# the clock and the process launch, as names the tests replace
now = time.time
sleep = time.sleep
Popen = subprocess.Popen


# --------------------------------------------------------------------------- the run
class SoakRefused(Exception):
    """The soak cannot start; nothing was changed."""


@dataclass
class Result:
    outcome: str
    detail: str = ""
    run_dir: Path | None = None
    checks: list = field(default_factory=list)      # (what, ok) for each guard check

    @property
    def ok(self) -> bool:
        return self.outcome == "clean exit" and all(ok for _, ok in self.checks)


def default_docs() -> Path:
    return Path.home() / "Documents" / "Paradox Interactive" / "Crusader Kings III"


def default_base() -> Path:
    """The tool's cache folder for soak runs and the lock: CK3SM_SOAK_DIR, else ``soak`` in the user cache folder
    (``%LOCALAPPDATA%\\ck3-save-migrator`` on Windows, ``$XDG_CACHE_HOME`` or ``~/.cache`` + ``ck3-save-migrator``
    elsewhere; the folder keeps the project's old name, like the config folder's)."""
    if os.environ.get("CK3SM_SOAK_DIR"):
        return Path(os.environ["CK3SM_SOAK_DIR"])
    if sys.platform == "win32" and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "ck3-save-migrator" / "soak"
    return Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "ck3-save-migrator" / "soak"


def game_exe(install: Path) -> Path:
    for name in ("ck3.exe", "ck3"):
        if (install / "binaries" / name).is_file():
            return install / "binaries" / name
    raise SoakRefused(f"no binaries/ck3.exe in {install} (give --game the install folder, the one that holds "
                      "'binaries' and 'game')")


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _crash_line(folder: Path) -> str:
    exc = folder / "exception.txt"
    if exc.is_file():
        for line in exc.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.strip():
                return line.strip()
    return f"(no exception.txt in {folder.name})"


def soak(save: Path, *, install: Path, docs: Path | None = None, base: Path | None = None, run_dir: Path | None = None,
         exit_after: int = 600, speed: int = 5, mods: list[str] | None = None, say=print) -> Result:
    """Run the soak; see the module docstring. Raises SoakRefused before changing anything when it cannot start."""
    docs = docs or default_docs()
    base = base or default_base()
    save = Path(save)
    if not save.is_file():
        raise SoakRefused(f"no save at {save}")
    if not 1 <= speed <= 5:
        raise SoakRefused(f"--speed is 1 to 5, not {speed}")
    exe = game_exe(install)
    saves_dir = docs / "save games"
    if not saves_dir.is_dir():
        raise SoakRefused(f"no 'save games' folder in {docs} (give --docs the game's documents folder)")
    for m in mods or []:
        if not (docs / m).is_file():
            raise SoakRefused(f"{m}: no such mod descriptor in {docs}")
    staged = saves_dir / f"{STAGED_PREFIX}{save.stem}.ck3"
    if staged.exists() and staged.read_bytes() != save.read_bytes():
        raise SoakRefused(f"{staged} exists and is not this save; not overwriting it")
    base.mkdir(parents=True, exist_ok=True)
    lock = base / "soak.lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise SoakRefused(f"another soak is running (lock {lock}; delete it if none is)") from None
    with os.fdopen(fd, "w") as f:
        f.write(f"{os.getpid()}\n")
    try:
        if game_running():
            raise SoakRefused("the game is already running; close it first")
        return _run(save, exe, docs, saves_dir, staged, base, run_dir, exit_after, speed, mods, say)
    finally:
        lock.unlink(missing_ok=True)


def _run(save, exe, docs, saves_dir, staged, base, run_dir, exit_after, speed, mods, say) -> Result:
    stamp = dt.datetime.now().strftime("%Y-%m-%d__%H-%M-%S")
    run = Path(run_dir) if run_dir else base / f"{stamp}__{save.stem}"
    (run / "autosave-guard").mkdir(parents=True, exist_ok=True)
    timeline = (run / "timeline.txt").open("a", encoding="utf-8")
    res = Result("did not load", run_dir=run)

    def note(msg: str) -> None:
        line = f"[{dt.datetime.now():%H:%M:%S}] {msg}"
        timeline.write(line + "\n")
        timeline.flush()
        say(msg)

    # 1. backups: every autosave, and dlc_load.json (or the fact that there is none)
    guarded = {}
    for f in sorted(saves_dir.glob("autosave*.ck3")):
        shutil.copy2(f, run / "autosave-guard" / f.name)
        guarded[f.name] = _sha(f)
        if _sha(run / "autosave-guard" / f.name) != guarded[f.name]:
            timeline.close()
            raise SoakRefused(f"the backup of {f.name} did not verify; nothing changed")
    note(f"autosave guard: {len(guarded)} file(s) backed up and hashed in {run / 'autosave-guard'}")
    dlc = docs / "dlc_load.json"
    dlc_before = dlc.read_bytes() if dlc.is_file() else None
    if dlc_before is not None:
        (run / "dlc_load.json").write_bytes(dlc_before)
    created_stage = not staged.exists()
    proc = None
    crashes = docs / "crashes"
    crashes_before = {p.name for p in crashes.iterdir()} if crashes.is_dir() else set()
    try:
        # 2. mods for this run only
        if mods:
            cfg = json.loads(dlc_before) if dlc_before else {"disabled_dlcs": []}
            cfg["enabled_mods"] = list(mods)
            dlc.write_text(json.dumps(cfg), encoding="utf-8")
            note(f"mods for this run: {', '.join(mods)}")
        # 3. stage the save and launch
        if created_stage:
            shutil.copy2(save, staged)
        note(f"staged {staged.name} ({'copied' if created_stage else 'already there, same bytes'})")
        cmd = [str(exe), "-gdpr-compliant", "-debug_mode", f"-loadsave={staged.name}"]
        (run / "cmdline.txt").write_text(" ".join(cmd) + "\n", encoding="utf-8")
        dpi_aware()
        note(f"launch: {' '.join(cmd)}")
        proc = Popen(cmd, cwd=str(exe.parent))
        res = _watch(proc, docs, crashes, crashes_before, exit_after, speed, note, res)
    finally:
        # 4. whatever happened: the game gone, the player's files put back, each check reported
        if proc is not None and proc.poll() is None:
            proc.terminate()
            note("stopped the game (it was still running)")
            for _ in range(15):
                if proc.poll() is not None:
                    break
                sleep(1)
        logs = docs / "logs"
        if logs.is_dir():
            shutil.copytree(logs, run / "logs", dirs_exist_ok=True)
        if crashes.is_dir():
            for p in crashes.iterdir():
                if p.name not in crashes_before:
                    shutil.copytree(p, run / "crashes" / p.name, dirs_exist_ok=True)
        for f in sorted(saves_dir.glob("autosave*.ck3")):
            if f.name not in guarded:
                shutil.move(str(f), str(run / f.name))
                note(f"autosave guard: the game's new {f.name} moved to the run folder")
            elif _sha(f) != guarded[f.name]:
                shutil.copy2(f, run / f"soak__{f.name}")
                shutil.copy2(run / "autosave-guard" / f.name, f)
                note(f"autosave guard: {f.name} changed; the game's copy kept as soak__{f.name}, yours restored")
        for name, h in guarded.items():
            cur = saves_dir / name
            ok = cur.exists() and _sha(cur) == h
            res.checks.append((f"autosave {name}", ok))
            note(f"autosave guard: {name} {'verified' if ok else 'NOT VERIFIED: restore it from ' + str(run / 'autosave-guard')}")
        if created_stage and staged.exists():
            staged.unlink()
            note(f"removed the staged {staged.name}")
        if dlc_before is None:
            dlc.unlink(missing_ok=True)
            ok = not dlc.exists()
        else:
            dlc.write_bytes(dlc_before)
            ok = dlc.read_bytes() == dlc_before
        res.checks.append(("dlc_load.json", ok))
        note(f"dlc_load.json {'restored, byte for byte' if ok else 'NOT RESTORED: the original is in ' + str(run)}")
        note(f"result: {res.outcome}{': ' + res.detail if res.detail else ''}")
        timeline.close()
    return res


def _watch(proc, docs, crashes, crashes_before, exit_after, speed, note, res: Result) -> Result:
    logs = docs / "logs"
    pos = {logs / n: (logs / n).stat().st_size for n in LOGS if (logs / n).exists()}
    t0 = now()
    hwnd = 0
    in_game_at = None
    keys_sent = False
    exit_posted_at = None
    exit_clicks = 0
    last_sig = None
    stuck = 0
    while True:
        rc = proc.poll()
        if rc is not None:
            break
        if not hwnd:
            hwnd = find_main_window(proc.pid)
            if hwnd:
                note(f"window 0x{hwnd:x}")
                send_to_back(hwnd)
        for name in LOGS:
            for line in tail_new(logs / name, pos):
                tags = [tag for rx, tag in WATCH if rx.search(line)]
                if "LOAD-FAILED" in tags:
                    note(f"{name}: {line[:300]}")
                    res.outcome, res.detail = "did not load", line.strip()[:300]
                    return res
                if "Setting idler 'In Game'" in line and in_game_at is None:
                    in_game_at = now()
                    note("in game")
        if crashes.is_dir():
            new = {p.name for p in crashes.iterdir()} - crashes_before
            if new:
                folder = crashes / sorted(new)[0]
                when = "crash on exit" if exit_posted_at is not None else "crash while running"
                res.outcome, res.detail = when, _crash_line(folder)
                note(f"crash folder {folder.name}: {res.detail}")
                return res
        if in_game_at is None and now() - t0 > LOAD_TIMEOUT:
            res.outcome, res.detail = "did not load", f"not in game after {LOAD_TIMEOUT // 60} minutes"
            return res
        if now() - t0 > LOAD_TIMEOUT + exit_after + EXIT_WAIT + 60:     # e.g. in game but no window ever found
            res.outcome, res.detail = "did not exit", f"no exit after {int(now() - t0)} s (window found: {bool(hwnd)})"
            return res
        if in_game_at is not None and hwnd and not keys_sent and now() - in_game_at > KEYS_DELAY:
            for k in ("space", str(speed)):
                post_key(hwnd, k)
            keys_sent = True
            note(f"keys: space, {speed} (unpaused, speed {speed})")
        if keys_sent and exit_posted_at is None:
            sig = date_signature(hwnd)
            if same_date(sig, last_sig):
                stuck += 1
                if stuck == 1:
                    post_key(hwnd, "space")
                    note("keepalive: the date did not move; space pressed once")
                elif stuck == 3:
                    note("keepalive: the date still does not move after the press; the game may be frozen")
            else:
                stuck = 0
            last_sig = sig
        if keys_sent and exit_posted_at is None and now() - in_game_at > exit_after:
            post_close(hwnd)
            exit_posted_at = now()
            note(f"exit: WM_CLOSE posted {exit_after}s after in game (opens the Exit Game dialog)")
        if exit_posted_at is not None:
            waited = now() - exit_posted_at
            if exit_clicks == 0 and waited > 4:
                note("exit: " + click_client(hwnd, *EXIT_TO_DESKTOP) + " (Exit to Desktop)")
                exit_clicks = 1
            elif exit_clicks == 1 and waited > 25:
                note("exit: still running; " + click_client(hwnd, *EXIT_TO_DESKTOP, real=True) + " (Exit to Desktop)")
                exit_clicks = 2
            if waited > EXIT_WAIT:
                res.outcome, res.detail = "did not exit", f"still running {EXIT_WAIT}s after WM_CLOSE"
                return res
        sleep(POLL)
    # the process ended: give the crash reporter time to write its folder, then say which way it went
    new = set()
    for _ in range(CRASH_WAIT // 2):
        new = ({p.name for p in crashes.iterdir()} - crashes_before) if crashes.is_dir() else set()
        if new:
            break
        sleep(2)
    if new:
        folder = crashes / sorted(new)[0]
        res.outcome = "crash on exit" if exit_posted_at is not None else "crash while running"
        res.detail = _crash_line(folder)
    elif exit_posted_at is not None:
        res.outcome, res.detail = "clean exit", f"exit code {rc}, no crash folder within {CRASH_WAIT} s"
    elif in_game_at is None:
        res.outcome, res.detail = "did not load", f"the game ended (exit code {rc}) before it was in game"
    else:
        res.outcome, res.detail = "crash while running", f"the game ended (exit code {rc}) with no crash folder"
    note(f"the game ended: {res.outcome} ({res.detail})")
    return res
