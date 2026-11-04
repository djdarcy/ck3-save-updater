"""close_game: ask a running ck3.exe to close the way a player does, and show what happened (the #40 goal's licence:
"a window close message, never taskkill or a forced kill"). Never kills anything.

Steps: find ck3.exe's main window; post WM_CLOSE (opens the game's "Exit Game" dialog); wait; screenshot the window
(window only, via the screenshot skill's shot.ps1) so the dialog can be seen; with --click X,Y (client fractions)
post a click there (the dialog's "Exit to Desktop"); wait up to --wait seconds for the process to end; report.

Usage: python -I tests/one-offs/close_game.py <out dir> [--click 0.5,0.55] [--real] [--wait 60] [--no-close]
"""
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import launch_load_test as L  # noqa: E402


def ck3_pid() -> int | None:
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq ck3.exe", "/FO", "CSV", "/NH"], capture_output=True,
                         text=True).stdout
    for line in out.splitlines():
        parts = [p.strip('"') for p in line.split('","')]
        if parts and parts[0].lower() == "ck3.exe":
            return int(parts[1])
    return None


def shot(hwnd: int, out: Path) -> None:
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(L.SHOT),
                    "-Hwnd", f"0x{hwnd:x}", "-Out", str(out)], capture_output=True, text=True, timeout=30)


def main(argv: list[str]) -> int:
    import ctypes
    # as launch_load_test does: without this, Windows scaling hands us a smaller client rect than the game's own,
    # and a click by fraction lands in the wrong place (2026-11-03: 2560x1440 against the game's 3840x2160)
    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))   # PER_MONITOR_AWARE_V2
    out = Path(argv[0])
    out.mkdir(parents=True, exist_ok=True)
    wait = int(argv[argv.index("--wait") + 1]) if "--wait" in argv else 60
    pid = ck3_pid()
    if pid is None:
        print("no ck3.exe running")
        return 0
    hwnd = L.find_main_window(pid)
    print(f"ck3.exe pid {pid}, window 0x{hwnd:x}")
    import ctypes
    if "--no-close" not in argv:
        ctypes.windll.user32.PostMessageW(hwnd, 0x0010, 0, 0)          # WM_CLOSE
        print("WM_CLOSE posted")
        time.sleep(4)
    shot(hwnd, out / f"{time.strftime('%H-%M-%S')}__after-close.png")
    if "--click" in argv:
        fx, fy = (float(v) for v in argv[argv.index("--click") + 1].split(","))
        print(L.click_client(hwnd, fx, fy, real="--real" in argv))
    t0 = time.time()
    while time.time() - t0 < wait:
        if ck3_pid() is None:
            print(f"exited {int(time.time() - t0)}s after the last step")
            return 0
        time.sleep(2)
    shot(hwnd, out / f"{time.strftime('%H-%M-%S')}__still-running.png")
    print(f"STILL RUNNING after {wait}s (pid {pid}); not killed")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
