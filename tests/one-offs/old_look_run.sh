#!/bin/bash
# The old look for #40's judge (S2): load a staged MIGRATE_TEST__ save in the full 1.8.2 build kept under
# private/data/versions/1.8.2, with only the 2023 portrait mods the founding save's faces were written with --
# CFP 3.1.5 (the save's own), EPE 1.6.0, the 2022 CFP+EPE patch and the stand-in tail layer (EPE's December 2022
# genes) -- never today's Workshop CFP/EPE. with_portrait_mods.py writes run-only MIGRATE_TEST__ descriptors,
# backs up dlc_load.json and restores it byte-exact; the game is closed normally (--h-exit-after: WM_CLOSE, then
# Exit to Desktop). Run docs_guard.py snapshot/check around a session of these runs: 1.8.2 shares the Documents folder.
# Usage: old_look_run.sh <run-name> <save file name in save games> [seconds in game before the close, default 60]
set -u
NAME="${1:?run name}"
SAVEFILE="${2:?save file name}"
WAITS="${3:-60}"
R="/c/code/ck3-save-migrator"
D="$R/private/data"
cd "$R"
python -I tests/one-offs/with_portrait_mods.py "$NAME" --only-also \
  --also "$D/mods-archive/cfp_3.1.5" \
  --also "$D/originals/mods-2023/epe_1.6.0" \
  --also "$D/originals/mods-2022.06.21/2507220129" \
  --also "$D/layers/epe_2022-12_tail" \
  -- python -I tests/one-offs/launch_load_test.py "$NAME" "--h-exe=$D/versions/1.8.2/binaries/ck3.exe" \
     -debug_mode "-loadsave=${SAVEFILE%.ck3}" "--h-exit-after=$WAITS"
# 2026-11-03: with "-loadsave=<name>.ck3" 1.8.2 stayed at the main menu (no load attempt in debug.log); the
# extension is dropped here. If it still does not load, 1.8.2 needs another route (-continuelastsave).
RUN=$(ls -td private/data/runs/*"$NAME" | head -1)
echo "run: $RUN"; ls "$RUN/shots" | tail -3
grep "In Game\|LOAD-FAILED\|stop:\|exit\|process after run" "$RUN/timeline.txt" | cut -c1-160
