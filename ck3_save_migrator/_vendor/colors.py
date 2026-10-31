"""ANSI color helpers for dazzlecmd-lib rendering.

Vendored into ck3-save-migrator (2026-10-31) from dazzlecmd-lib ``dazzlecmd_lib/colors.py`` at commit a4a35fb
(sha256 ca77faa61125ce27...), copied byte for byte and then changed only as follows: ``BLUE`` added (info lines;
the same constant was released upstream in dazzlecmd-lib 0.10.35a0, so the two copies do not drift), and ``CK3UPDATE_COLOR`` read with the
same values and precedence as ``DZ_COLOR`` (either one may force color on or off). Everything below is upstream's
text; its docstrings still name dazzlecmd-lib.

Slim by design: 8-color ANSI palette only (broadly supported including PuTTY,
Windows Terminal, modern conhost.exe with VT processing, bash/zsh, WSL). No
truecolor escapes (256-color or RGB) because those break older terminals.

The lib's render functions (`render_list`, `render_info`, `render_tree`,
`render_kit_list`, plus stderr warnings) call `should_use_color()` to decide
whether to emit color, then wrap text via `colorize(text, *codes)`.

Detection priority (in `should_use_color`):
1. ``NO_COLOR`` env var set (any value)  -> False (community standard)
2. ``DZ_COLOR=always`` OR ``FORCE_COLOR`` env var set -> True (force on)
3. ``DZ_COLOR=never`` -> False (project-specific override)
4. ``stream.isatty()`` -> True if the stream is a TTY, else False

Windows compatibility:
- Modern Windows (Win10 1511+, Win11) handles ANSI natively via
  ``ENABLE_VIRTUAL_TERMINAL_PROCESSING`` in conhost.exe.
- Legacy cmd.exe needs ``colorama`` to translate ANSI -> Windows Console API.
- This module lazily imports ``colorama`` and calls ``colorama.init()`` on
  Windows when ``should_use_color()`` first returns True. Missing colorama
  is non-fatal -- modern Windows works without it.

Install with ``pip install dazzlecmd-lib[color]`` to add colorama as a
Windows-only optional extra. Adding colorama to required deps is rejected
by the lib's slim-default constraint.

Public API:
    RESET, BOLD, DIM, RED, GREEN, YELLOW, BLUE, CYAN, BRIGHT_RED  -- ANSI constants
    should_use_color(stream=None) -> bool                    -- TTY+env probe
    colorize(text: str, *codes: str) -> str                  -- wrap helper
    colorize_for(stream, text, *codes) -> str                -- TTY-gated wrap
    warn(text: str, stream=None) -> str                      -- YELLOW (stderr)
    error(text: str, stream=None) -> str                     -- BRIGHT_RED (stderr)
"""

from __future__ import annotations

import os
import sys

# 8-color ANSI palette + bold/dim emphasis. Compatible with PuTTY, cmd.exe
# (post-VT-mode), PowerShell, Windows Terminal, conhost, bash, zsh, WSL.
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
CYAN = "\033[36m"
BRIGHT_RED = "\033[91m"

# Track colorama init so we only attempt it once per process. The init is
# a no-op on non-Windows platforms but the import attempt costs ~1ms.
_ansi_initialized = False


def _init_windows_ansi(force=False):
    """Lazily import and initialize colorama on Windows.

    ``force=True`` -> ``colorama.init(strip=False)``. Used when the caller
    explicitly forces color (``DZ_COLOR=always`` / ``FORCE_COLOR``) and
    output is piped: without ``strip=False``, colorama strips ANSI when
    not writing to a real console, which defeats the explicit force.

    ``force=False`` -> ``colorama.init()`` (default). On a real Windows
    console, colorama translates ANSI to Windows Console API calls. When
    piped, ANSI is stripped (the polite default for ``isatty=True`` paths
    where the user hasn't asked for forced color).

    Silent no-op if colorama isn't installed (modern Windows 1511+ handles
    ANSI natively via VT processing; only legacy cmd.exe truly needs
    colorama).
    """
    try:
        import colorama  # type: ignore[import-not-found]
        if force:
            colorama.init(strip=False)
        else:
            colorama.init()
    except ImportError:
        pass


def should_use_color(stream=None) -> bool:
    """Return True if ANSI color should be emitted to ``stream``.

    Detection priority:
    1. ``NO_COLOR`` env var set (any value)  -> False (community standard).
    2. ``DZ_COLOR=always`` OR ``FORCE_COLOR`` set -> True.
    3. ``DZ_COLOR=never`` -> False.
    4. ``stream.isatty()`` -> True/False.

    Default stream: ``sys.stdout``. Pass ``sys.stderr`` for warning paths.

    Side effect: on the first call that returns True on Windows, attempts to
    initialize colorama (silently no-ops if colorama isn't installed). This
    is idempotent; subsequent calls don't re-init.
    """
    global _ansi_initialized

    # NO_COLOR (industry standard: https://no-color.org/) -- absolute override
    if os.environ.get("NO_COLOR") is not None:
        return False

    dz_color = (os.environ.get("CK3UPDATE_COLOR") or os.environ.get("DZ_COLOR", "")).lower()

    # Force-on cases: user explicitly wants color even when piped.
    # On Windows, pass force=True so colorama keeps the ANSI codes intact
    # (its default strips them when output isn't a real console).
    if dz_color == "always" or os.environ.get("FORCE_COLOR"):
        if not _ansi_initialized and sys.platform == "win32":
            _init_windows_ansi(force=True)
            _ansi_initialized = True
        return True

    # Force-off case
    if dz_color == "never":
        return False

    # Default: gate on isatty. On a real Windows console, colorama
    # translates ANSI to Win Console API; when piped it strips, which
    # is the right default for "polite" auto-detected color.
    target = stream if stream is not None else sys.stdout
    is_tty = hasattr(target, "isatty") and target.isatty()
    if is_tty and not _ansi_initialized and sys.platform == "win32":
        _init_windows_ansi(force=False)
        _ansi_initialized = True
    return is_tty


def colorize(text: str, *codes: str) -> str:
    """Wrap ``text`` in ANSI ``codes``, terminated with ``RESET``.

    Returns ``text`` unchanged when ``codes`` is empty. Designed so the
    caller can do:

        from dazzlecmd_lib.colors import colorize, BOLD, should_use_color

        styled = colorize(label, BOLD) if should_use_color() else label
        print(styled)

    Or for the common pattern where color is conditional:

        codes = (BOLD,) if should_use_color() else ()
        print(colorize(label, *codes))

    No automatic TTY check here -- callers control when to apply color so
    that data-shape APIs (like ``build_list_entries``) remain plain.
    """
    if not codes:
        return text
    return "".join(codes) + text + RESET


def colorize_for(stream, text: str, *codes: str) -> str:
    """Convenience wrapper: colorize ``text`` only when ``should_use_color(stream)``.

    Designed for the common stderr-warning pattern where a single line
    of code must decide both whether to color AND wrap the text:

        import sys
        from dazzlecmd_lib.colors import colorize_for, YELLOW

        print(colorize_for(sys.stderr, f"Warning: {msg}", YELLOW),
              file=sys.stderr)

    Equivalent to:

        if should_use_color(stream):
            ... colorize(text, *codes) ...
        else:
            ... text ...

    but collapses the conditional into one expression so the call site
    stays scannable.
    """
    if should_use_color(stream):
        return colorize(text, *codes)
    return text


def warn(text: str, stream=None) -> str:
    """Format ``text`` as a warning. YELLOW + RESET when color is enabled
    on ``stream`` (defaults to ``sys.stderr``); plain ``text`` otherwise.

    Semantic shortcut for the common pattern:

        print(colorize_for(sys.stderr, f"Warning: {msg}", YELLOW),
              file=sys.stderr)

    Usage:

        import sys
        from dazzlecmd_lib.colors import warn

        print(warn(f"Tool {tool!r} not found."), file=sys.stderr)

    Pairs with ``error()`` for the two most common stderr-message classes.
    Callers wanting a non-standard emphasis (e.g. BOLD+YELLOW for a banner)
    should call ``colorize_for`` directly with their own codes.
    """
    target = stream if stream is not None else sys.stderr
    return colorize_for(target, text, YELLOW)


def error(text: str, stream=None) -> str:
    """Format ``text`` as an error. BRIGHT_RED + RESET when color is enabled
    on ``stream`` (defaults to ``sys.stderr``); plain ``text`` otherwise.

    Semantic shortcut for the common pattern:

        print(colorize_for(sys.stderr, f"Error: {exc}", BRIGHT_RED),
              file=sys.stderr)

    Usage:

        import sys
        from dazzlecmd_lib.colors import error

        print(error(f"Error: cannot read config: {exc}"), file=sys.stderr)

    Use BRIGHT_RED rather than RED to stay visible on dark terminals where
    plain RED is hard to read.
    """
    target = stream if stream is not None else sys.stderr
    return colorize_for(target, text, BRIGHT_RED)
