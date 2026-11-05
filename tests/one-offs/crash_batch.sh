#!/bin/bash
# Repeat the observer-mode console-save run on several staged saves, alternating, to tell an intermittent crash in our
# output from one the game has anyway (2026-11-04: 2 crashes in 3 runs on ours, 0 in 1 on the vanilla reference).
# Each run: observe, top speed, console save after SECS seconds, guarded autosaves, dlc_load restored, then
# docs_guard restore. Prints one line per run. Usage: crash_batch.sh <rounds> <secs> <save name> [<save name> ...]
set -u
ROUNDS="${1:?rounds}"; SECS="${2:?seconds}"; shift 2
R="/c/code/ck3-save-migrator"
cd "$R"
for i in $(seq 1 "$ROUNDS"); do
  for SAVE in "$@"; do
    tag="${SAVE%.ck3}"; tag="${tag#MIGRATE_TEST__}"
    if tasklist //FI "IMAGENAME eq ck3.exe" | grep -qi ck3; then echo "round $i $tag: GAME ALREADY RUNNING, stopping"; exit 1; fi
    bash tests/one-offs/play7_shots.sh "crashbatch-$tag-$i" "$SAVE" "$SECS" "--h-console=observe" --h-key=space --h-key=5 \
      --h-keepalive --h-guard-autosave "--h-exit-console=save MIGRATE_TEST__cb_${tag}_$i" > /dev/null 2>&1
    RUN=$(ls -td private/data/runs/*"crashbatch-$tag-$i" | head -1)
    res=$(grep -h "exit result" "$RUN/timeline.txt" | tail -1 | sed 's/.*exit result: //')
    saved=$(ls "/c/Users/Extreme/Documents/Paradox Interactive/Crusader Kings III/save games/MIGRATE_TEST__cb_${tag}_$i.ck3" 2>/dev/null && echo yes || echo no)
    python -I tests/one-offs/docs_guard.py restore plzwork > /dev/null 2>&1
    echo "round $i $tag: $res; console save written: ${saved##*/}"
    # stop at once if the user's autosaves or Documents did not come back (2026-11-04: two autosaves lost silently)
    if grep -q "NOT VERIFIED" "$RUN/timeline.txt" || ! python -I tests/one-offs/docs_guard.py check plzwork 2>&1 | tail -1 | grep -q "^0 differences"; then
      echo "round $i $tag: the user's files did not verify; stopping"; exit 2
    fi
  done
done
