"""For each key the game still fails to read (a list file of "<count> <key>:" lines, from error.log), find the save
field that holds it: the key right before "=", or the key of the one-line list it sits in, plus the top-level section.
Usage: python -I lost_key_fields.py <save.ck3> <lost.txt>"""
import re
import sys
from collections import Counter, defaultdict

sys.path.insert(0, r"C:\code\ck3-save-migrator")
from ck3_save_migrator import savefile as sf  # noqa: E402

d = sf.read_save(sys.argv[1]).gamestate
keys = [ln.split()[1].rstrip(":") for ln in open(sys.argv[2], encoding="utf-8") if len(ln.split()) > 1]
tops = [(m.start(), m.group(1).decode()) for m in re.finditer(rb"(?m)^([A-Za-z_][\w]*)=", d)]
starts = [t[0] for t in tops]

import bisect  # noqa: E402

for key in keys:
    fields, sections = Counter(), Counter()
    for m in re.finditer(rb"(?<![\w.\-])\"?" + re.escape(key.encode()) + rb"\"?(?![\w.\-])", d):
        s = m.start()
        if d[s - 1:s] == b"=":
            k = s - 1
            j = k
            while j > 0 and d[j - 1] not in b" \t\r\n{}":
                j -= 1
            fields[d[j:k].decode(errors="replace")] += 1
        else:
            brace, close, nl = d.rfind(b"{", 0, s), d.rfind(b"}", 0, s), d.rfind(b"\n", 0, s)
            if brace > max(close, nl):
                j = brace - 1
                while j > 0 and d[j - 1] not in b" \t\r\n{}":
                    j -= 1
                fields["[" + d[j:brace - 1].decode(errors="replace") + "]"] += 1
            else:
                fields["<other>"] += 1
        i = bisect.bisect_right(starts, s) - 1
        sections[tops[i][1] if i >= 0 else "?"] += 1
    print(f"{key:48s} {dict(fields.most_common(3))}  in {dict(sections.most_common(3))}")
