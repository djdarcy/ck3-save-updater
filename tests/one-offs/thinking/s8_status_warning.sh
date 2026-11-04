#!/bin/bash
# S8 (#40): does `status` warn that the source layout is not the save's? Runs status on the founding save three ways
# and prints R19's lines: (a) without --old-portrait-mods, (b) with the 2023 CFP + EPE 1.6.0, (c) with the tail
# layer too. The expectation in the goal: (a) warns, (b)/(c) do not. Read-only: status writes nothing.
R="C:/code/ck3-save-migrator"
S="$R/private/data/faces/acc"
SAVE="$R/private/data/originals/save games/Arch-Abbot_Beidh_of_Omni_Church_Council_987_10_27_husband_died.ck3"
REF="$R/private/data/originals/reference-1.20/ref_1_20_987_10_27.ck3"
OLD="$R/private/data/versions/1.8.2/game"
M23="$R/private/data/originals/mods-2023"
TAIL="$R/private/data/layers/epe_2022-12_tail"
export CK3SM_CONFIG="$S/cfg/config.toml" CK3UPDATE_CACHE_DIR="$S/cache" PYTHONIOENCODING=utf-8 PYTHONPATH="$R"
cd "$R"
run() {
  echo "== $1"
  shift
  python -m ck3_save_migrator status "$SAVE" --old-game-dir "$OLD" --portrait-mods 2220098919,2507209632,2996881191 \
    --reference "$REF" "$@" 2>&1 | grep -nE "R19|FACES|source:|template ind|probably not|faces in another|longer than|shorter" | head -20
}
run "(a) no --old-portrait-mods"
run "(b) cfp_3.1.11 + epe_1.6.0" --old-portrait-mods "$M23/cfp_3.1.11,$M23/epe_1.6.0"
run "(c) + the tail layer" --old-portrait-mods "$M23/cfp_3.1.11,$M23/epe_1.6.0,$TAIL"
