#!/usr/bin/env bash
# ck3_catch_write.sh -- attach to the running game and stop at the instruction that writes a given value into a
# landed title's in-memory field (a hardware write breakpoint, conditional on the value), print the call stack and
# the registers there, then detach and let the game run on.
#
# 2026-10-27: c_kuzeytorg's liege-title field (+0xE8) flips from k_pontic_steppe to the county itself on 987.11.8,
# after which the game's "which kingdom" routine loops forever. This finds the writer.
#
# Usage: bash tests/one-offs/ck3_catch_write.sh <title slot, decimal> <field offset, hex> <value, hex> <out file> [timeout s]
set -u
SLOT="$1"; FIELD="$2"; VALUE="$3"; OUT="$4"; TMO="${5:-600}"
CDB="/c/Program Files (x86)/Windows Kits/10/Debuggers/x64/cdb.exe"
PID=$(tasklist //FI "IMAGENAME eq ck3.exe" //FO CSV //NH | head -1 | cut -d, -f2 | tr -d '"')
[ -n "$PID" ] || { echo "ck3.exe is not running"; exit 1; }
OFF=$(printf '0x%x' $((8 + SLOT * 16)))
CMDS="r \$t0 = poi(poi(ck3+0x5d32b08)+0x20)+$OFF; r \$t1 = poi(@\$t0)+$FIELD; .printf \"watching %p (now %x)\\n\", @\$t1, dwo(@\$t1); "
CMDS+="ba w4 @\$t1 \".if (dwo(@\$t1) == $VALUE) { .printf \\\"HIT value %x\\\\n\\\", dwo(@\$t1); r; kn 40; ~*k 3; .detach; q } .else { gc }\"; g"
# -pd: if cdb is ended (the timeout), it detaches instead of killing the game
timeout "$TMO" "$CDB" -pd -p "$PID" -c "$CMDS" > "$OUT" 2>&1
echo "exit $?; $(grep -c HIT "$OUT") hit(s); output in $OUT"
