"""split_decompile: turn a headless DecompileAt.java run's log into one .c file per function.

Each "==== ck3+0x... (addr) ..." block of the log becomes <out>/ck3+0x....c, with the call and string lines kept
as a comment header and Ghidra's log prefixes removed. Prints the files written.

Usage: python -I tests/one-offs/ghidra/split_decompile.py <ghidra log> <out folder> [--note "text for each header"]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

PREFIX = re.compile(r"^INFO  DecompileAt\.java> ?")
SUFFIX = re.compile(r" \(GhidraScript\)\s*$")


def main():
    log, out = Path(sys.argv[1]), Path(sys.argv[2])
    note = sys.argv[sys.argv.index("--note") + 1] if "--note" in sys.argv else ""
    out.mkdir(parents=True, exist_ok=True)
    blocks, cur = [], None
    for raw in log.read_text(encoding="utf-8", errors="replace").splitlines():
        if not PREFIX.match(raw) and cur is not None and raw.startswith("INFO "):
            continue                                  # other headless log lines
        line = SUFFIX.sub("", PREFIX.sub("", raw))
        m = re.match(r"^==== (ck3\+0x[0-9a-f]+) \(([0-9a-f]+)\)", line)
        if m:
            cur = {"name": m.group(1), "addr": m.group(2), "head": [], "body": []}
            blocks.append(cur)
            continue
        if cur is None:
            continue
        # a decompiled function is one log message: its first line carries the prefix, the rest follow bare
        if line.startswith(("  call ", "  str ")):
            cur["head"].append(line.strip())
        else:
            cur["body"].append(line)
    for b in blocks:
        path = out / f"{b['name']}.c"
        head = [f"// {b['name']} (image address 0x{b['addr']}), Crusader Kings III 1.20.1.2 ck3.exe",
                "// Decompiled by Ghidra 12.1 headless, imported without auto-analysis (DecompileAt.java).",
                "// Names are Ghidra's placeholders; no symbols exist for this binary."]
        if note:
            head.append(f"// {note}")
        head += [f"// {h}" for h in b["head"]]
        path.write_text("\n".join(head + [""] + [x for x in b["body"] if x.strip() or True]).rstrip() + "\n",
                        encoding="utf-8")
        print(f"wrote {path} ({len(b['body'])} lines)")


if __name__ == "__main__":
    main()
