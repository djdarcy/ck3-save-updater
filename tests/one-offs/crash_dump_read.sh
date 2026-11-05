#!/bin/bash
# Read a CK3 crash folder's minidump with cdb: the exception record, the faulting instruction as an offset from ck3's
# image base (ck3+0x...), the registers and the stack, plus the function entry of the faulting address (for
# Ghidra's DecompileAt.java). Writes the output into private/code/ck3/<version>/stacks/ and prints it.
# Usage: crash_dump_read.sh <crash folder> <label> [game version, default 1.20.1.2]
set -u
CDB="/c/Program Files (x86)/Windows Kits/10/Debuggers/x64/cdb.exe"
DIR="${1:?crash folder}"; LABEL="${2:?label}"; VER="${3:-1.20.1.2}"
R="/c/code/ck3-save-migrator"
OUT="$R/private/code/ck3/$VER/stacks/$(date +%Y-%m-%d)__crash__$LABEL.txt"
DUMP="$(cygpath -w "$DIR/minidump.dmp")"
GAME="E:\\SteamLibrary\\steamapps\\common\\Crusader Kings III\\binaries"
# .ecxr switches to the exception context; kn shows the frames; r the registers; u the faulting instructions
"$CDB" -z "$DUMP" -i "$GAME" -y "$GAME" -c ".exr -1; .ecxr; r; kn 30; ub @rip L8; u @rip L4; q" > "$OUT" 2>&1
grep -E 'ExceptionAddress|ExceptionCode|Attempt to|ck3\+|rax=|rbx=|rcx=|rdx=|rsi=|rdi=|r8=' "$OUT" | head -50
echo "written: $OUT"
