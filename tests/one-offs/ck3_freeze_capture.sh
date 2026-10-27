#!/usr/bin/env bash
# ck3_freeze_capture.sh -- when the game's date has stopped although it is unpaused, record which thread spins and,
# if it is the known "which kingdom" loop (ck3+0x23187e0..0x2318830), which title it is stuck on.
# Writes <out>/stacks.txt (busiest threads and all stacks) and <out>/loop_title.txt (one line per thread whose rip
# is inside the loop: thread, rip, the title id [rbx+0x10], its climbed field [rbx+0xE8], its holder [rbx+0x128]).
#
# Usage: bash tests/one-offs/ck3_freeze_capture.sh <out folder>
set -u
OUT="$1"; mkdir -p "$OUT"
CDB="/c/Program Files (x86)/Windows Kits/10/Debuggers/x64/cdb.exe"
PID=$(tasklist //FI "IMAGENAME eq ck3.exe" //FO CSV //NH | head -1 | cut -d, -f2 | tr -d '"')
[ -n "$PID" ] || { echo "ck3.exe is not running"; exit 1; }
"$CDB" -pv -p "$PID" -c "lm m ck3; !runaway 3; ~*k 20; qd" > "$OUT/stacks.txt" 2>&1
"$CDB" -pv -p "$PID" -c "~*e .printf \"thread %x rip=%p rbx=%p id=%x e8=%x holder=%x\\n\", @\$tid, @rip, @rbx, dwo(@rbx+0x10), dwo(@rbx+0xe8), dwo(@rbx+0x128); qd" 2>&1 \
  | grep -E "^thread" > "$OUT/all_threads.txt"
# the army/AI movement freeze (989.8.28, under ck3+0x19f73dc): the unit object is rsi in that function's frame; read
# the frame registers of the busiest thread's stack frames 1-3 and the first words of rsi's object in each
"$CDB" -pv -p "$PID" -c "~5s; kn 6; .frame /r 1; dq @rsi L12; .frame /r 2; dq @rsi L12; dd @rsi+0x10 L2; dq poi(@rsi+0x58) L4; .frame /r 3; qd" \
  > "$OUT/unit_frames.txt" 2>&1
python -I - "$OUT" <<'EOF'
import re, sys
out = sys.argv[1]
base = None
for line in open(out + "/stacks.txt", encoding="utf-8", errors="replace"):
    m = re.search(r"^([0-9a-f]{8}`[0-9a-f]{8})\s+[0-9a-f]{8}`[0-9a-f]{8}\s+ck3\b", line, re.I)   # `lm m ck3` row
    if m:
        base = int(m.group(1).replace("`", ""), 16)
        break
rows = []
for line in open(out + "/all_threads.txt", encoding="utf-8"):
    m = re.search(r"rip=([0-9a-f`]+)", line)
    if m and base:
        off = int(m.group(1).replace("`", ""), 16) - base
        if 0x23187e0 <= off <= 0x2318830:
            rows.append(f"{line.strip()} (ck3+0x{off:x})")
open(out + "/loop_title.txt", "w").write("\n".join(rows) + "\n")
print("in the loop:", rows if rows else "none (not the known loop; see stacks.txt)")
EOF
