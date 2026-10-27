#!/usr/bin/env bash
# watch_title_field.sh -- read one landed title's in-memory fields in the running game every few seconds
# (non-invasive cdb attach). From the decompiled loop at ck3+0x23186e0 (2026-10-27): titles live in a table at
# [ck3+0x5d32b08]; entry = poi(poi(table+0x20) + 8 + slot*0x10); [entry+0x10] = the title's id, [entry+0x14] = the
# "Land" tag, [entry+0xE8] = the field the freezing loop climbs, [entry+0x108] and [entry+0x128] = the fields the
# function reads first. Prints one line per read: time, the four values (hex).
#
# Usage: bash tests/one-offs/watch_title_field.sh <title slot, decimal> <reads> [gap seconds]
set -u
SLOT="$1"; N="$2"; GAP="${3:-10}"
CDB="/c/Program Files (x86)/Windows Kits/10/Debuggers/x64/cdb.exe"
PID=$(tasklist //FI "IMAGENAME eq ck3.exe" //FO CSV //NH | head -1 | cut -d, -f2 | tr -d '"')
[ -n "$PID" ] || { echo "ck3.exe is not running"; exit 1; }
OFF=$(printf '0x%x' $((8 + SLOT * 16)))
for i in $(seq 1 "$N"); do
  line=$("$CDB" -pv -p "$PID" -c "r \$t0 = poi(poi(ck3+0x5d32b08)+0x20)+$OFF; r \$t1 = poi(@\$t0); .printf \"id=%x tag=%x e8=%x f108=%x f128=%x\\n\", dwo(@\$t1+0x10), dwo(@\$t1+0x14), dwo(@\$t1+0xe8), dwo(@\$t1+0x108), dwo(@\$t1+0x128); qd" 2>&1 | grep -E "^id=")
  echo "$(date +%H:%M:%S) $line"
  sleep "$GAP"
done
