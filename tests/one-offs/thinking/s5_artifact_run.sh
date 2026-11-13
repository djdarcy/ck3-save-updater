#!/usr/bin/env bash
# MEASURE S5 (finding F21): load the artifact-edited copy and save at once (zero days), by the method of S0(c)'s run
# in s0b_runs.sh: a docs_guard snapshot right before, a console save, a normal close (by PID only after 60 s), and a
# restore against that same snapshot. Stops at once if ck3.exe is already running (it would be djdarcy's game).
# Run from the repo root: bash tests/one-offs/thinking/s5_artifact_run.sh <path to MIGRATE_TEST__s5_artifact.ck3>
set -u
cd /c/code/ck3-save-migrator || exit 1
src="$1"
saves="/c/Users/Extreme/Documents/Paradox Interactive/Crusader Kings III/save games"
name="MIGRATE_TEST__s5_artifact"
out="MIGRATE_TEST__s5_artifact_resaved"
case "$(basename "$src")" in MIGRATE_TEST__*) ;; *) echo "STOP: not a MIGRATE_TEST__ save"; exit 2;; esac
if tasklist //FI "IMAGENAME eq ck3.exe" | grep -qi ck3.exe; then
  echo "STOP: ck3.exe is running (not ours); ask before going on"; exit 3
fi
cp "$src" "$saves/$name.ck3" || exit 5
snap=$(python -I tests/one-offs/docs_guard.py snapshot plzwork 2>&1 | tail -1 | sed -E 's/^snapshot (.*): [0-9]+ protected.*/\1/')
[ -d "$snap" ] || { echo "STOP: could not read the snapshot path ($snap)"; exit 4; }
echo "[s5a] snapshot: $snap"
timeout 400 python -I tests/one-offs/launch_load_test.py s5-artifact "--h-console=save $out" \
  --h-exit-after=45 --h-max=300 --h-guard-autosave -debug_mode "-loadsave=$name.ck3" > /dev/null 2>&1
r=$(ls -td private/data/runs/*s5-artifact | head -1)
echo "[s5a] run folder: $r"
grep -E 'taskkill|exit result|crash' "$r/timeline.txt" | tail -3 | sed "s/^/[s5a] /"
ls -la "$saves/$out.ck3" 2>&1 | sed "s/^/[s5a] /"
python -I tests/one-offs/docs_guard.py restore plzwork --backup "$snap" 2>&1 | tail -1 | sed "s/^/[s5a] /"
tasklist //FI "IMAGENAME eq ck3.exe" | tail -1 | sed "s/^/[s5a] /"
