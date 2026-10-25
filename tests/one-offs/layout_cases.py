"""Count the layout cases a gamestate scanner must handle, in real extracted gamestates.

Usage: python -I tests/one-offs/layout_cases.py <gamestate> [<gamestate> ...]
"""
import re
import sys
from pathlib import Path

PATTERNS = {
    "tabbed multi-key line": rb"\n\t+[a-z_]+=[a-z_0-9]+\t+[a-z_]+=",
    "rgb value": rb"=rgb \{",
    "hsv value": rb"=hsv\d* \{",
    "empty key (tab then =)": rb"\n\t+=",
    "escaped quote": rb'\\"',
    "id=none scalar at col 0": rb"\n\d+=none\n",
    "anonymous list item line": rb"\n \{\n",
    "quoted key": rb'\n\t*"[^"\n]+"=',
}

for path in sys.argv[1:]:
    data = Path(path).read_bytes()
    print(f"== {Path(path).parent.name} ({len(data):,} bytes)")
    for name, pat in PATTERNS.items():
        ms = list(re.finditer(pat, data))
        ex = repr(data[ms[0].start():ms[0].start() + 80]) if ms else ""
        print(f"  {name:26} {len(ms):>9,}  {ex}")
