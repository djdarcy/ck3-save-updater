#!/usr/bin/env bash
# MEASURE S0(b): three observe-mode runs (control A, control B, reseeded), each a fresh docs_guard snapshot before,
# a console save after ~200 s at speed, a normal close (the launcher's ladder; by PID only after 60 s), and a restore
# against that run's own snapshot. Stops at once if ck3.exe is already running (it would be djdarcy's game).
# Run from the repo root: bash tests/one-offs/thinking/s0b_runs.sh
set -u
cd /c/code/ck3-save-migrator || exit 1
run() {   # $1 run name, $2 save to load, $3 save name to write
  if tasklist //FI "IMAGENAME eq ck3.exe" | grep -qi ck3.exe; then
    echo "STOP: ck3.exe is running (not ours); ask before going on"; exit 3
  fi
  # the path holds a drive colon (C:\...), so cut at ": <n> protected", never at the first colon (2026-11-09: the
  # first version cut at "C" and every restore failed)
  snap=$(python -I tests/one-offs/docs_guard.py snapshot plzwork 2>&1 | tail -1 | sed -E 's/^snapshot (.*): [0-9]+ protected.*/\1/')
  [ -d "$snap" ] || { echo "STOP: could not read the snapshot path ($snap)"; exit 4; }
  echo "[$1] snapshot: $snap"
  timeout 600 python -I tests/one-offs/launch_load_test.py "$1" --h-console=observe --h-key=plus --h-key=plus \
    --h-key=plus --h-key=plus --h-key=space --h-pause-before-exit "--h-exit-console=save $3" --h-exit-after=40 --h-max=400 \
    --h-guard-autosave -debug_mode "-loadsave=$2" > /dev/null 2>&1
  r=$(ls -td private/data/runs/*"$1" | head -1)
  grep -E 'taskkill|exit result|crash' "$r/timeline.txt" | tail -2 | sed "s/^/[$1] /"
  head -c 3000 "/c/Users/Extreme/Documents/Paradox Interactive/Crusader Kings III/save games/$3.ck3" 2>/dev/null \
    | grep -a -m1 meta_date | sed "s/^/[$1] /"
  python -I tests/one-offs/docs_guard.py restore plzwork --backup "$snap" 2>&1 | tail -1 | sed "s/^/[$1] /"
}
# second batch (2026-11-09 ~02:55): paused before the save, ~40 s at speed (the first ran 200 s = 5.5 years, and both
# controls crashed on the running save)
run s0b2-control-a MIGRATE_TEST__play14.ck3 MIGRATE_TEST__s0b2_control_a
run s0b2-control-b MIGRATE_TEST__play14.ck3 MIGRATE_TEST__s0b2_control_b
run s0b2-reseeded MIGRATE_TEST__s0b_reseeded.ck3 MIGRATE_TEST__s0b2_reseeded
# S0(c) in the same window: load the artifact copy and save at once (zero days), as S0(a)'s first pair did
if tasklist //FI "IMAGENAME eq ck3.exe" | grep -qi ck3.exe; then echo "STOP before s0c: ck3.exe is running"; exit 3; fi
snap=$(python -I tests/one-offs/docs_guard.py snapshot plzwork 2>&1 | tail -1 | sed -E 's/^snapshot (.*): [0-9]+ protected.*/\1/')
[ -d "$snap" ] || { echo "STOP: could not read the snapshot path ($snap)"; exit 4; }
timeout 400 python -I tests/one-offs/launch_load_test.py s0c-artifact "--h-console=save MIGRATE_TEST__s0c_artifact_resaved" \
  --h-exit-after=45 --h-max=300 --h-guard-autosave -debug_mode -loadsave=MIGRATE_TEST__s0c_artifact.ck3 > /dev/null 2>&1
r=$(ls -td private/data/runs/*s0c-artifact | head -1)
grep -E 'taskkill|exit result|crash' "$r/timeline.txt" | tail -2 | sed "s/^/[s0c] /"
python -I tests/one-offs/docs_guard.py restore plzwork --backup "$snap" 2>&1 | tail -1 | sed "s/^/[s0c] /"
tasklist //FI "IMAGENAME eq ck3.exe" | tail -1
