"""Profile the key schema of one top-level section of a CK3 gamestate, or compare two.

Usage:
  python -I profile_section.py <gamestate> <section> [--entries N] [--depth D] [--strlen KEY ...]
  python -I profile_section.py <gamestate_a> <gamestate_b> <section> [--entries N] [--depth D] [--strlen KEY ...]

Walks the section with a small Clausewitz tokenizer (no full parse of 222 MB): entries are the
section's direct children; keys are counted per depth so "faith= appears in 36,700 of 36,700
entries" and "rite= appears in 0" become numbers. --strlen KEY prints a length histogram of the
quoted values of KEY (DNA blobs, flag bitsets). With two gamestates the two profiles are printed
side by side with the entry-fraction of each key, so renames and removals stand out.
"""
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

TOK = re.compile(rb'"(?:[^"\\]|\\.)*"|[{}=]|[^\s{}="]+')


def section_bytes(path: Path, key: str) -> bytes:
    data = path.read_bytes()
    m = re.search(rb"^" + key.encode() + rb"\s*=\s*\{", data, re.M)
    if not m:
        raise SystemExit(f"{key} not found in {path}")
    # find the matching close brace by scanning
    depth = 0
    i = m.end() - 1
    n = len(data)
    while i < n:
        c = data[i]
        if c == 0x7B:
            depth += 1
        elif c == 0x7D:
            depth -= 1
            if depth == 0:
                return data[m.end():i]
        elif c == 0x22:  # skip quoted strings
            j = data.find(b'"', i + 1)
            while j != -1 and data[j - 1] == 0x5C:
                j = data.find(b'"', j + 1)
            i = j if j != -1 else n
        i += 1
    return data[m.end():]


def profile(body: bytes, max_entries: int, max_depth: int, strlen_keys: set[str]):
    """Return (entry_count, key_presence[depth][key] = number of entries containing it, strlens)."""
    toks = TOK.findall(body)
    presence = defaultdict(Counter)
    strlens = defaultdict(Counter)
    entries = 0
    depth = 0           # 0 = section level; entries live at depth 1
    stack = []          # key path; stack[d] = key at depth d
    seen_in_entry = set()
    pending_key = None
    i = 0
    n = len(toks)
    while i < n:
        t = toks[i]
        if t == b"=":
            i += 1
            continue
        if t == b"{":
            if pending_key is not None:
                stack.append(pending_key)
            else:
                stack.append(b"{}")   # anonymous block in a list
            depth += 1
            if depth == 1:
                entries += 1
                seen_in_entry = set()
                if entries > max_entries:
                    break
            pending_key = None
            i += 1
            continue
        if t == b"}":
            depth -= 1
            if stack:
                stack.pop()
            pending_key = None
            i += 1
            continue
        # a scalar token: key if followed by "=", else a value
        nxt = toks[i + 1] if i + 1 < n else None
        if nxt == b"=":
            if depth >= 1 and depth <= max_depth:
                path = b"/".join(stack[1:depth] + [t]).decode(errors="replace")
                if path not in seen_in_entry:
                    seen_in_entry.add(path)
                    presence[depth][path] += 1
                if t.decode(errors="replace") in strlen_keys and i + 2 < n and toks[i + 2].startswith(b'"'):
                    strlens[t.decode()][len(toks[i + 2]) - 2] += 1
            pending_key = t
            i += 2
            continue
        pending_key = None
        i += 1
    return entries, presence, strlens


def show(label, entries, presence, strlens, max_depth):
    print(f"== {label}: {entries:,} entries")
    for d in range(1, max_depth + 1):
        if not presence[d]:
            continue
        print(f"-- depth {d} keys (count = entries containing the key)")
        for k, c in presence[d].most_common():
            print(f"   {c:>8,}  {k}")
    for k, hist in strlens.items():
        print(f"-- value lengths of {k}: " + ", ".join(f"{ln}:{c}" for ln, c in sorted(hist.items())[:12]))


def inner_bytes(body: bytes, inner: str) -> bytes:
    """Descend into a named child block of a section body (e.g. landed_titles -> landed_titles, relations -> active_relations)."""
    for name in inner.split("/"):
        # the child must sit at depth 0 of the current body, not be a same-named list deeper down
        m = None
        depth = 0
        i = 0
        n = len(body)
        pat = re.compile(rb"(?m)^\s*" + name.encode() + rb"\s*=\s*\{")
        for cand in pat.finditer(body):
            while i < cand.start():
                c = body[i]
                if c == 0x7B:
                    depth += 1
                elif c == 0x7D:
                    depth -= 1
                elif c == 0x22:
                    j = body.find(b'"', i + 1)
                    i = j if j != -1 else n
                i += 1
            if depth == 0:
                m = cand
                break
        if not m:
            raise SystemExit(f"inner block {name} not found at depth 0")
        depth, i, n = 0, m.end() - 1, len(body)
        while i < n:
            c = body[i]
            if c == 0x7B:
                depth += 1
            elif c == 0x7D:
                depth -= 1
                if depth == 0:
                    body = body[m.end():i]
                    break
            elif c == 0x22:
                j = body.find(b'"', i + 1)
                i = j if j != -1 else n
            i += 1
    return body


def main(argv):
    opts = {"--entries": 50000, "--depth": 2}
    strlen_keys = set()
    inner = None
    pos = []
    i = 0
    while i < len(argv):
        if argv[i] in opts:
            opts[argv[i]] = int(argv[i + 1]); i += 2
        elif argv[i] == "--strlen":
            strlen_keys.add(argv[i + 1]); i += 2
        elif argv[i] == "--inner":
            inner = argv[i + 1]; i += 2
        else:
            pos.append(argv[i]); i += 1
    max_entries, max_depth = opts["--entries"], opts["--depth"]

    def load(path, key):
        body = section_bytes(Path(path), key)
        return inner_bytes(body, inner) if inner else body

    if len(pos) == 2:
        e, p, s = profile(load(pos[0], pos[1]), max_entries, max_depth, strlen_keys)
        show(f"{pos[1]}{'/' + inner if inner else ''} in {Path(pos[0]).parent.name}", e, p, s, max_depth)
        return
    a, b, key = pos
    ea, pa, sa = profile(load(a, key), max_entries, max_depth, strlen_keys)
    eb, pb, sb = profile(load(b, key), max_entries, max_depth, strlen_keys)
    la, lb = Path(a).parent.name, Path(b).parent.name
    print(f"== {key}: A={la} ({ea:,} entries)   B={lb} ({eb:,} entries)")
    for d in range(1, max_depth + 1):
        keys = sorted(set(pa[d]) | set(pb[d]), key=lambda k: -(pa[d][k] + pb[d][k]))
        if not keys:
            continue
        print(f"-- depth {d}:   A%      B%    key")
        for k in keys:
            fa = pa[d][k] / ea * 100 if ea else 0
            fb = pb[d][k] / eb * 100 if eb else 0
            mark = "  " if (fa and fb) else ("A " if fa else " B")
            print(f"   {mark} {fa:6.1f}  {fb:6.1f}   {k}")
    for k in strlen_keys:
        print(f"-- {k} value lengths  A: " + ", ".join(f"{ln}:{c}" for ln, c in sorted(sa[k].items())[:10]))
        print(f"-- {k} value lengths  B: " + ", ".join(f"{ln}:{c}" for ln, c in sorted(sb[k].items())[:10]))


if __name__ == "__main__":
    main(sys.argv[1:])
