"""A spinner that loops in place on stderr while a slow step runs, with a line saying which step.

The frame themes are copied from wtf-restarted (``wtf_restarted/output/spinners.py`` at 0bcc10b, sha256
1ac56f98...), where Rich draws them; here a small thread draws them, so no Rich dependency. Each theme is a dict
with 'interval' (ms) and 'frames' (list of single chars).

Usage:
    with Spinner(enabled=spinner_wanted(sys.stderr)) as sp:
        sp.update("checking R23 nickname-text (11 of 12)")

Drawn only on a terminal: off under a pipe, ``NO_COLOR``, ``--plain``, ``-q`` and ``--json`` (the caller decides
with ``spinner_wanted``). While a long regular-expression scan holds the interpreter, the frame pauses; the line
still changes at every step.
"""

import os
import shutil
import sys
import threading
import time

# -- Star family: point -> cross -> star -> burst -> breathe back --

SPINNERS = {
    # 6 frames, Rich's built-in star set -- smooth same-weight morph
    "star-simple": {
        "interval": 70,
        "frames": list("\u2736\u2738\u2739\u273a\u2739\u2737"),
        # ✶ ✸ ✹ ✺ ✹ ✷
    },
    # 8 frames, clean and fast
    "star-breathe": {
        "interval": 80,
        "frames": list("\u00b7\u271b\u2726\u2739\u273a\u2739\u2726\u271b"),
        # · ✛ ✦ ✹ ✺ ✹ ✦ ✛
    },
    # 12 frames, adds thin cross and simple star
    "star-crescendo": {
        "interval": 80,
        "frames": list("\u00b7\u2719\u271b\u2726\u2736\u2739\u273a\u2739\u2736\u2726\u271b\u2719"),
        # · ✙ ✛ ✦ ✶ ✹ ✺ ✹ ✶ ✦ ✛ ✙
    },
    # 16 frames, full crescendo with asterisk peak
    "star-full": {
        "interval": 70,
        "frames": list("\u00b7\u2719\u271b\u2726\u2736\u2738\u2739\u273a\u273b\u273a\u2739\u2738\u2736\u2726\u271b\u2719"),
        # · ✙ ✛ ✦ ✶ ✸ ✹ ✺ ✻ ✺ ✹ ✸ ✶ ✦ ✛ ✙
    },

    # -- Dot family: minimal, works everywhere --

    # 6 frames, subtle dot pulse
    "dot-pulse": {
        "interval": 120,
        "frames": list("\u00b7\u2219\u2022\u25cf\u2022\u2219"),
        # · ∙ • ● • ∙
    },

    # -- Cross family: rotational feel --

    # 8 frames, cross morphing
    "cross-morph": {
        "interval": 100,
        "frames": list("\u253c\u2719\u271b\u271c\u2722\u271c\u271b\u2719"),
        # ┼ ✙ ✛ ✜ ✢ ✜ ✛ ✙
    },

    # -- Diamond family: angular shapes --

    # 8 frames, diamond to star
    "diamond-star": {
        "interval": 90,
        "frames": list("\u00b7\u2726\u2727\u2736\u2737\u2736\u2727\u2726"),
        # · ✦ ✧ ✶ ✷ ✶ ✧ ✦
    },

    # -- Sparkle family: decorative, high visual interest --

    # 10 frames, sparkle burst
    "sparkle": {
        "interval": 80,
        "frames": list("\u00b7\u2726\u2736\u2738\u273b\u273a\u2749\u273a\u273b\u2738"),
        # · ✦ ✶ ✸ ✻ ✺ ❉ ✺ ✻ ✸
    },

    # -- Minimal family: for quiet/professional contexts --

    # 4 frames, just a blinking dot
    "dot-blink": {
        "interval": 300,
        "frames": [" ", "\u00b7", "\u2219", "\u00b7"],
        #   · ∙ ·
    },
    # 6 frames, gentle arc
    "arc": {
        "interval": 100,
        "frames": list("\u25dc\u25e0\u25dd\u25de\u25e1\u25df"),
        # ◜ ◠ ◝ ◞ ◡ ◟
    },
}

# Default spinner for the application
DEFAULT_SPINNER = "star-breathe"


# for a stream whose encoding cannot write the themes' characters (a legacy console code page)
ASCII = {"interval": 120, "frames": list("|/-\\")}


def spinner_wanted(stream, *, plain: bool = False, quiet: int = 0, json_out: bool = False) -> bool:
    """Draw a spinner on ``stream``: only on a terminal, and never under ``--plain``, ``-q``, ``--json`` or
    ``NO_COLOR`` (whose output must read the same pasted as on screen)."""
    if plain or quiet > 0 or json_out or os.environ.get("NO_COLOR", "") != "":
        return False
    try:
        return bool(stream.isatty())
    except (AttributeError, ValueError):
        return False


def _theme(stream, name: str) -> dict:
    theme = SPINNERS.get(name, SPINNERS[DEFAULT_SPINNER])
    try:
        "".join(theme["frames"]).encode(getattr(stream, "encoding", None) or "ascii")
    except (UnicodeEncodeError, LookupError):
        return ASCII
    return theme


class Spinner:
    """One status line, redrawn in place: ``<frame> <text>  <seconds> s``. A context manager: the line is erased
    on every exit, an exception included. Disabled, it writes nothing and starts no thread."""

    def __init__(self, enabled: bool, stream=None, theme: str = DEFAULT_SPINNER):
        self.enabled = enabled
        self.stream = stream if stream is not None else sys.stderr
        self.theme = _theme(self.stream, theme) if enabled else ASCII
        self.text = ""
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._thread = None
        self._drawn = 0                 # the width of what is on the line now
        self._t0 = time.perf_counter()

    def __enter__(self):
        if self.enabled:
            self._t0 = time.perf_counter()
            self._thread = threading.Thread(target=self._run, name="ck3update-spinner", daemon=True)
            self._thread.start()
        return self

    def __exit__(self, *exc):
        self.stop()
        return False

    def update(self, text: str) -> None:
        """The stage now running; drawn at once (a long step may hold the interpreter before the next tick)."""
        self.text = text
        if self.enabled:
            self._draw(self._frame)

    @property
    def _frame(self) -> str:
        frames = self.theme["frames"]
        return frames[int((time.perf_counter() - self._t0) * 1000 / self.theme["interval"]) % len(frames)]

    def _draw(self, frame: str) -> None:
        width = max(20, shutil.get_terminal_size((80, 24)).columns - 1)   # one short of the edge: no wrap
        secs = f"  {time.perf_counter() - self._t0:.0f} s"
        line = f"{frame} {self.text}"[:width - len(secs)] + secs
        with self._lock:
            if self._stop.is_set():
                return
            self.stream.write("\r" + line + " " * max(0, self._drawn - len(line)))
            self.stream.flush()
            self._drawn = len(line)

    def _run(self) -> None:
        while not self._stop.wait(self.theme["interval"] / 1000):
            self._draw(self._frame)

    def stop(self) -> None:
        """Stop the thread and erase the line, leaving the cursor at its start."""
        if not self.enabled or self._stop.is_set():
            self._stop.set()
            return
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
        with self._lock:
            if self._drawn:
                self.stream.write("\r" + " " * self._drawn + "\r")
                self.stream.flush()
                self._drawn = 0
