#!/usr/bin/env bash
# ck3_stack_sample.sh -- thread stacks of a running ck3.exe, taken non-invasively (cdb -pv: the threads are
# suspended for the moment of the read and resumed on detach; the game keeps running). Two samples, $GAP s apart,
# so a thread that stays busy in the same frames is visible as a loop, not a slow tick.
#
# Usage: bash tests/one-offs/ck3_stack_sample.sh <out folder> [gap seconds]
set -u
OUT="$1"; GAP="${2:-20}"
mkdir -p "$OUT"
CDB="/c/Program Files (x86)/Windows Kits/10/Debuggers/x64/cdb.exe"
PID=$(tasklist //FI "IMAGENAME eq ck3.exe" //FO CSV //NH | head -1 | cut -d, -f2 | tr -d '"')
[ -n "$PID" ] || { echo "ck3.exe is not running"; exit 1; }
for n in 1 2; do
  "$CDB" -pv -p "$PID" -c ".symfix+ c:\\symcache; !runaway 3; ~*k 30; qd" > "$OUT/sample_$n.txt" 2>&1
  echo "sample $n written ($(wc -l < "$OUT/sample_$n.txt") lines)"
  [ "$n" = 1 ] && sleep "$GAP"
done
