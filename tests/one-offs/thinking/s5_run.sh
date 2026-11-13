#!/usr/bin/env bash
# MEASURE S5 (finding F20): one observe-mode run of the event-edited copy, by the method of s0b_runs.sh's second
# batch (the controls it is compared against): a docs_guard snapshot right before, ~40 s at speed, a pause, a console
# save, a normal close (the launcher's ladder; by PID only after 60 s), and a restore against that same snapshot.
# Stops at once if ck3.exe is already running (it would be djdarcy's game).
# The test save is made beforehand by the tool's own edits (see SAVE-FINDINGS F20) and copied into the save games
# folder under its MIGRATE_TEST__ name by this script.
# Run from the repo root: bash tests/one-offs/thinking/s5_run.sh <path to MIGRATE_TEST__s5_events.ck3>
set -u
cd /c/code/ck3-save-migrator || exit 1
src="$1"
saves="/c/Users/Extreme/Documents/Paradox Interactive/Crusader Kings III/save games"
name="MIGRATE_TEST__s5_events"
out="MIGRATE_TEST__s5_events_run"
case "$(basename "$src")" in MIGRATE_TEST__*) ;; *) echo "STOP: not a MIGRATE_TEST__ save"; exit 2;; esac
if tasklist //FI "IMAGENAME eq ck3.exe" | grep -qi ck3.exe; then
  echo "STOP: ck3.exe is running (not ours); ask before going on"; exit 3
fi
cp "$src" "$saves/$name.ck3" || exit 5
snap=$(python -I tests/one-offs/docs_guard.py snapshot plzwork 2>&1 | tail -1 | sed -E 's/^snapshot (.*): [0-9]+ protected.*/\1/')
[ -d "$snap" ] || { echo "STOP: could not read the snapshot path ($snap)"; exit 4; }
echo "[s5] snapshot: $snap"
timeout 600 python -I tests/one-offs/launch_load_test.py s5-events --h-console=observe --h-key=plus --h-key=plus \
  --h-key=plus --h-key=plus --h-key=space --h-pause-before-exit "--h-exit-console=save $out" --h-exit-after=40 --h-max=400 \
  --h-guard-autosave -debug_mode "-loadsave=$name.ck3" > /dev/null 2>&1
r=$(ls -td private/data/runs/*s5-events | head -1)
echo "[s5] run folder: $r"
grep -E 'taskkill|exit result|crash' "$r/timeline.txt" | tail -3 | sed "s/^/[s5] /"
head -c 3000 "$saves/$out.ck3" 2>/dev/null | grep -a -m1 meta_date | sed "s/^/[s5] /"
python -I tests/one-offs/docs_guard.py check plzwork --backup "$snap" 2>&1 | tail -2 | sed "s/^/[s5] check: /"
python -I tests/one-offs/docs_guard.py restore plzwork --backup "$snap" 2>&1 | tail -1 | sed "s/^/[s5] /"
tasklist //FI "IMAGENAME eq ck3.exe" | tail -1 | sed "s/^/[s5] /"
