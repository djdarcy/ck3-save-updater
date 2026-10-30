"""pe_xref: find x64 code that references an address in a PE file, by RIP-relative operands. (2026-10-28)

Ghidra was imported without auto-analysis (ck3.exe is 101 MB), so it has no cross-references. This finds them the
cheap way: locate a string (or take an address), then scan the executable sections for every 4-byte RIP-relative
displacement that resolves to it -- LEA, MOV, CMP, CALL alike -- and print the referencing instruction's address
(as ck3+offset) and the enclosing function's start from the .pdata unwind table.

Usage: python -I tests/one-offs/pe_xref.py <exe> --string PORTRAIT_CACHE_EXPIRE_FRAMES
       python -I tests/one-offs/pe_xref.py <exe> --rva 0x5c7c0d8 [--rva ...]
"""
from __future__ import annotations

import bisect
import struct
import sys


def sections(data):
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    nsec = struct.unpack_from("<H", data, pe + 6)[0]
    opt = struct.unpack_from("<H", data, pe + 20)[0]
    base = struct.unpack_from("<Q", data, pe + 24 + 24)[0]
    dd = pe + 24 + 112
    pdata_rva, pdata_size = struct.unpack_from("<II", data, dd + 3 * 8)
    out = []
    for i in range(nsec):
        o = pe + 24 + opt + i * 40
        name = data[o:o + 8].rstrip(b"\0").decode()
        vsize, rva, rsize, raw = struct.unpack_from("<IIII", data, o + 8)
        chars = struct.unpack_from("<I", data, o + 36)[0]
        out.append((name, rva, vsize, raw, rsize, chars))
    return base, out, (pdata_rva, pdata_size)


def rva_to_off(secs, rva):
    for _, s_rva, vs, raw, rs, _ in secs:
        if s_rva <= rva < s_rva + max(vs, rs):
            return raw + rva - s_rva
    return None


def off_to_rva(secs, off):
    for _, s_rva, vs, raw, rs, _ in secs:
        if raw <= off < raw + rs:
            return s_rva + off - raw
    return None


def main():
    a = sys.argv[1:]
    data = open(a[0], "rb").read()
    base, secs, (p_rva, p_size) = sections(data)
    targets = []
    if "--string" in a:
        s = a[a.index("--string") + 1].encode()
        i = data.find(s + b"\0")
        while i != -1:
            targets.append(off_to_rva(secs, i))
            i = data.find(s + b"\0", i + 1)
        print(f"string {s.decode()!r} at rva {[hex(t) for t in targets]}")
    for i, x in enumerate(a):
        if x == "--rva":
            targets.append(int(a[i + 1], 16))
    po = rva_to_off(secs, p_rva)
    starts = []
    for k in range(p_size // 12):
        b, e, _ = struct.unpack_from("<III", data, po + 12 * k)
        starts.append(b)
    starts.sort()
    tset = set(targets)
    for name, s_rva, vs, raw, rs, chars in secs:
        if not chars & 0x20000000:  # executable
            continue
        mv = memoryview(data)[raw:raw + rs]
        for j in range(0, rs - 4):
            disp = struct.unpack_from("<i", mv, j)[0]
            # the instruction ends after the displacement (no immediate) or after a 1/4-byte immediate
            for tail in (0, 1, 4):
                end_rva = s_rva + j + 4 + tail
                if end_rva + disp in tset:
                    ins = s_rva + j
                    f = starts[bisect.bisect_right(starts, ins) - 1] if starts else 0
                    print(f"  ref to 0x{end_rva + disp:x} near ck3+0x{ins:x} (disp at, tail {tail}); function ck3+0x{f:x}"
                          f"  bytes {bytes(mv[max(0, j - 3):j + 4 + tail]).hex()}")


if __name__ == "__main__":
    main()
