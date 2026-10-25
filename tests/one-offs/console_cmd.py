"""Type a command into CK3's debug console (game launched with -debug_mode) and capture the result.

Usage: python -I console_cmd.py <hwnd-hex> "<command>" [shots-dir]
Focuses the window for ~3 s (the only way keystrokes reach the game), opens the console with the
backtick key, types the command, presses Enter, captures the window, closes the console, and
sends the window back behind everything else.
"""
import ctypes
import subprocess
import sys
import time
from pathlib import Path

import pyautogui

SHOT = Path.home() / ".claude" / "skills" / "screenshot" / "shot.ps1"


def shot(hwnd: int, out: Path) -> None:
    subprocess.run(["pwsh", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(SHOT),
                    "-Hwnd", f"0x{hwnd:x}", "-Out", str(out)], capture_output=True, text=True, timeout=30,
                   stdin=subprocess.DEVNULL)


def main(hwnd: int, command: str, shots: Path | None) -> None:
    u = ctypes.windll.user32
    u.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    u.ShowWindow(hwnd, 9)
    time.sleep(1.0)
    u.SetForegroundWindow(hwnd)
    time.sleep(0.8)
    pyautogui.FAILSAFE = False
    pyautogui.press("`")
    time.sleep(1.0)
    pyautogui.typewrite(command, interval=0.03)
    time.sleep(0.3)
    if shots:
        shot(hwnd, shots / "console-typed.png")
    pyautogui.press("enter")
    time.sleep(1.5)
    if shots:
        shot(hwnd, shots / "console-after-enter.png")
    pyautogui.press("`")
    time.sleep(0.5)
    u.SetWindowPos(hwnd, 1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)  # HWND_BOTTOM, no size/move/activate
    print(f"sent: {command}")


if __name__ == "__main__":
    main(int(sys.argv[1], 16), sys.argv[2], Path(sys.argv[3]) if len(sys.argv) > 3 else None)
