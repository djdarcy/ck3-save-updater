"""Is every non-numeric key at column 0 of a gamestate a top-level section (no duplicates)?

Usage: python -I tests/one-offs/col0_keys.py <gamestate> [...]
"""
import re
import sys
from collections import Counter
from pathlib import Path

for path in sys.argv[1:]:
    data = Path(path).read_bytes()
    keys = [m.group(1) for m in re.finditer(rb"(?m)^([A-Za-z_][\w.]*)\s*=", data)]
    c = Counter(keys)
    dup = {k.decode(): n for k, n in c.items() if n > 1}
    print(f"{Path(path).parent.name}: {len(keys)} col-0 non-numeric keys, {len(c)} unique, duplicates: {dup or 'none'}")
