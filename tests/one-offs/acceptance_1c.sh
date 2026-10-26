#!/usr/bin/env bash
# Step 1c acceptance chain: migrate -> stage as MIGRATE_TEST__<tag>_faith -> the game's load and console save ->
# barony_seam.py and empty_provinces.py on the pair.
#
# Usage: bash tests/one-offs/acceptance_1c.sh <tag>
# Inputs, from the environment (no defaults, so no machine's paths live here):
#   CK3_CAMPAIGN   the 1.8.1 campaign save          CK3_REFERENCE  the 1.20 reference save at the same date
#   CK3_GAME       the 1.20 game folder             CK3_OLD_GAME   the 1.8.2 game folder
#   CK3_SAVES      the game's "save games" folder   CK3_OUT        a folder for outputs and probe results
set -u
for v in CK3_CAMPAIGN CK3_REFERENCE CK3_GAME CK3_OLD_GAME CK3_SAVES CK3_OUT; do
  [ -n "${!v:-}" ] || { echo "set $v"; exit 1; }
done
TAG="$1"
cd "$(dirname "$0")/../.." || exit 1
python -m ck3_save_migrator migrate "$CK3_CAMPAIGN" --rules R1,R2,R3,R4,R5,R6,R11,R8,R10,R9,R12,R15,R14,R16,R7 \
  --reference "$CK3_REFERENCE" --game-dir "$CK3_GAME" --old-game-dir "$CK3_OLD_GAME" --wos-shape faith \
  -o "$CK3_OUT/e2e_${TAG}__wos-faith.ck3" --report "$CK3_OUT/e2e_${TAG}.report.json" --force \
  > "$CK3_OUT/e2e_${TAG}.txt" 2>&1 || { echo "migrate failed"; exit 2; }
echo "migrate ok"
cp "$CK3_OUT/e2e_${TAG}__wos-faith.ck3" "$CK3_SAVES/MIGRATE_TEST__e2e${TAG}_faith.ck3"
cmp "$CK3_OUT/e2e_${TAG}__wos-faith.ck3" "$CK3_SAVES/MIGRATE_TEST__e2e${TAG}_faith.ck3" || { echo "stage mismatch"; exit 3; }
python -I tests/one-offs/launch_load_test.py "resave-e2e${TAG}" "--h-console=save MIGRATE_TEST__e2e${TAG}_faith__resaved" \
  --h-max=180 --h-guard-autosave -debug_mode "-loadsave=MIGRATE_TEST__e2e${TAG}_faith.ck3" \
  > "$CK3_OUT/resave_${TAG}.txt" 2>&1
[ -f "$CK3_SAVES/MIGRATE_TEST__e2e${TAG}_faith__resaved.ck3" ] || { echo "no re-save written"; exit 4; }
echo "resave ok"
python -I tests/one-offs/barony_seam.py "$CK3_CAMPAIGN" "$CK3_SAVES/MIGRATE_TEST__e2e${TAG}_faith.ck3" \
  "$CK3_SAVES/MIGRATE_TEST__e2e${TAG}_faith__resaved.ck3" "$CK3_OLD_GAME/common/landed_titles" \
  "$CK3_GAME/common/landed_titles" 83378 > "$CK3_OUT/barony_seam_e2e${TAG}.txt" 2>&1
python -I tests/one-offs/empty_provinces.py "$CK3_CAMPAIGN" "$CK3_SAVES/MIGRATE_TEST__e2e${TAG}_faith__resaved.ck3" \
  "$CK3_REFERENCE" "$CK3_GAME/common/landed_titles" > "$CK3_OUT/empty_provinces_e2e${TAG}_resaved.txt" 2>&1
echo "done"
