"""Names a player types and names the tool prints: accent folding, and output that never dies on a character.

The game's display names carry accents ("Ise Jingū", "Ásatrú", "Jórvík"); a Windows console that is piped or
redirected writes cp1252, which cannot hold some of them. Design: 2026-11-17__01-12-44__dev-workflow-process__name-
lists-and-the-games-display-names.md; goal 2026-11-17__01-24-33__goal__multi-word-names-across-the-tool.md.
"""
from __future__ import annotations

import codecs
import sys
import unicodedata

FOLD_ERRORS = "ck3fold"


def fold_accents(text: str) -> str:
    """The same text with accents taken off the letters: "Ise Jingū" -> "Ise Jingu", "Ásatrú" -> "Asatru".
    Letters with no plain form (伊勢, ß) are kept as they are."""
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def _fold_handler(err: UnicodeEncodeError):
    """Codec error handler: what an encoding cannot hold is written accent-folded, and as '?' when even that fails."""
    out = []
    for c in fold_accents(err.object[err.start:err.end]):
        try:
            c.encode(err.encoding)
            out.append(c)
        except (UnicodeEncodeError, LookupError):
            out.append("?")
    return "".join(out), err.end


codecs.register_error(FOLD_ERRORS, _fold_handler)


def safe_output(*streams) -> None:
    """Make each text stream (stdout and stderr by default) write accent-folded text instead of raising when its
    encoding cannot hold a character. An interactive Windows console, which takes any character, is unchanged in
    effect; a pipe or a redirect in cp1252 gets "Shinto Way" where it would have crashed on "Shintō Way"."""
    for s in streams or (sys.stdout, sys.stderr):
        # a Windows pipe measured 2026-11-17: cp1252 with errors="surrogateescape", which still raises on a real
        # character the encoding lacks (it only round-trips undecodable bytes)
        if getattr(s, "errors", None) in ("strict", "surrogateescape") and hasattr(s, "reconfigure"):
            try:
                s.reconfigure(errors=FOLD_ERRORS)
            except (ValueError, OSError):       # a stream that cannot be reconfigured keeps its behaviour
                pass
