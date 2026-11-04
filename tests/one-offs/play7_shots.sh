#!/bin/bash
# Screenshot play7 (= the 0.4.0 output, byte for byte) with the Claude playset (djdarcy's go, 2026-11-03: "You can
# switch to the playset as I'm afk on my phone"). dlc_load.json is backed up, written, and restored byte for byte.
# Moved from the 2026-11-03 session scratchpad (play7_claude_shots.sh) for the #40 goal; generalised to any staged save.
# Usage: play7_shots.sh [run-name] [save file name in save games] [seconds before STOP]
#   defaults: faces040-play7-claude MIGRATE_TEST__play7.ck3 60 (seconds in game before the normal close)
#   any further arguments go to launch_load_test.py as harness options (2026-11-04, the culture goal's U0), e.g.
#   "--h-console=save MIGRATE_TEST__u0_resaved" for a first-day re-save (the game starts paused)
set -u
NAME="${1:-faces040-play7-claude}"
SAVEFILE="${2:-MIGRATE_TEST__play7.ck3}"
WAITS="${3:-60}"
HARNESS=("${@:4}")
D="/c/Users/Extreme/Documents/Paradox Interactive/Crusader Kings III"
R="/c/code/ck3-save-migrator"
B="$R/private/data/backups/$(date +%Y-%m-%d__%H-%M-%S)__dlc_load.json"
mkdir -p "$R/private/data/backups"
cp -p "$D/dlc_load.json" "$B"
before=$(sha256sum "$D/dlc_load.json" | cut -c1-64)
restore() {
  cp -p "$B" "$D/dlc_load.json"
  after=$(sha256sum "$D/dlc_load.json" | cut -c1-64)
  echo "restored dlc_load.json: $([ "$before" = "$after" ] && echo byte-identical || echo DIFFERS) ($B)"
}
trap restore EXIT
python -I -c "
import json, sys
mods = ['mod/zz_hitch_no_cathedral_alert.mod', 'mod/ugc_2220098919.mod', 'mod/ugc_2507209632.mod', 'mod/ugc_2996881191.mod',
        'mod/ugc_2220326926.mod', 'mod/ugc_2531691049.mod', 'mod/ugc_2453009990.mod', 'mod/ugc_2535753142.mod',
        'mod/ugc_2600114033.mod', 'mod/ugc_2216754325.mod', 'mod/ugc_3811584019.mod', 'mod/ugc_3084203091.mod',
        'mod/ugc_2886198939.mod', 'mod/wos_1_20.mod', 'mod/ugc_2243723476.mod', 'mod/ugc_2227658180.mod',
        'mod/ugc_2221952570.mod', 'mod/ugc_2226700455.mod']
json.dump({'enabled_mods': mods, 'disabled_dlcs': []}, open(sys.argv[1], 'w', encoding='utf-8'))
" "$D/dlc_load.json"
echo "wrote the Claude playset into dlc_load.json"
cd "$R"
# 2026-11-03: the game now closes itself normally ($WAITS s after it is in game: WM_CLOSE, then Exit to Desktop),
# instead of a STOP file that left ck3.exe open; launch_load_test notes whether the process is still running.
python -I tests/one-offs/launch_load_test.py "$NAME" -gdpr-compliant -debug_mode "-loadsave=$SAVEFILE" "--h-exit-after=$WAITS" "${HARNESS[@]}"
RUN=$(ls -td private/data/runs/*"$NAME" | head -1)
echo "run: $RUN"; ls "$RUN/shots"; grep "In Game\|stop:\|exit\|process after run" "$RUN/timeline.txt" | cut -c1-160
