# The reference save

Several rules copy what they need from a save written by the current game: the religion rules (R8 to R12) rebuild religion from it, and the new-map rules (R14 to R16) bring in the regions 1.20 added, with their rulers, courts and families. That save is the reference, passed to `migrate` as `--reference`.

For religion, any 1.20 save will do; one at the same start date is closest. For the new-map regions it matters much more: the reference should be a fresh 1.20 game started on your campaign's own date. The new regions' people are copied as they are in the reference, so the reference has to show the world at the same moment as your campaign.

## Why a mod is needed

The game starts new games only on its bookmark dates. Unless your campaign happens to be on one of them, there is no way to start a 1.20 game on its date from the menu. The way around it is a small local mod that adds one bookmark on your date. `ck3update reference-mod` writes that mod for you.

## Steps

1. **Write the mod**, giving your campaign's save so the date is read from it:

   ```bash
   ck3update reference-mod --save "My_Old_Campaign"
   ```

   It goes into the game's own `mod` folder (in your documents folder, under `Paradox Interactive/Crusader Kings III/mod`, found the way the save folder is, OneDrive included); `--out "<folder>"` writes it somewhere else.

   Or give the date yourself with `--date <y.m.d>` (the in-game date shown on the load screen; the save records it as `meta_date`).

   A bookmark has to name a playable character: someone alive on your date who holds a title then. The tool picks one from the game's own history files (`history/characters` and `history/titles` in the game folder, found as `inspect` finds it, or `--game-dir`). Only a ruler whose culture, faith, dynasty house and birth date are all found is picked; among those it prefers an adult who holds a kingdom or a duchy; among equals, the first title key, so the pick is the same every run. Culture, faith and house are read as they stand on your date. The faith is the character's `rite` (as 1.20's history files write it; older games' `religion` is read too). Most characters name a numeric `dynasty` rather than a house, so the house is that dynasty's house from `common/dynasty_houses` (its only one; else its first that is not marked a cadet branch; else its first defined). The government is the title's own from its history, else `feudal_government`. It prints who was picked and why, and how the house was found. When no living title holder has all four facts, it refuses and says what the first one lacked, rather than write an incomplete bookmark.

   Any of `--character`, `--title`, `--culture`, `--religion`, `--house`, `--birth`, `--name`, `--government` and `--female` overrides what the history says; with `--character` alone, the tool checks that this character is alive and holds a title on the date, and reads the rest. With every one of the first six given, the game folder is not needed.

   It writes a folder `zz_ref_<date>` (holding `descriptor.mod`, the bookmark and its English text; the bookmark and the text are UTF-8 with a byte-order mark, as the game expects) and, beside it, `zz_ref_<date>.mod`, which the launcher reads. It refuses to overwrite either if it already exists.
2. **Enable the mod** in the game's launcher: it is listed as "Reference bookmark `<date>` (ck3update)". Use a playset with nothing else that changes bookmarks.
3. **Start a new game** from the bookmark named "`<date>` Reference (ck3update)", with any character, and **save at once**, before unpausing, so the world is exactly as the game starts it on that date.
4. **Run `status`, then `update`.** They find that save by themselves in the save folder: a save written by the game you have, on your campaign's date, preferring one made with this bookmark mod. Name it with `--reference "<path>"` when several could match (`status` lists them).

   ```bash
   ck3update status "My_Old_Campaign" --transplant auto
   ck3update update "My_Old_Campaign" --transplant auto
   ```

Disable the mod again for your normal games; it only adds a bookmark.

## Example: 27 October 987, choosing the ruler by hand

This is how the first reference was made, before the tool picked the ruler itself, and how to choose a particular ruler. Brian Boruma (history id 900) holds the duchy of Munster (`d_munster`) from 978.7.1, and the Irish titles are feudal from 935.1.1 (the game's `history/titles/k_ireland.txt`). He was born on 941.1.1, is Irish, of the insular Celtic faith and of the house of Briain:

```bash
ck3update reference-mod --date 987.10.27 --character 900 --title d_munster --culture irish --religion insular_celtic --house house_british_isles_briain --birth 941.1.1 --name "Brian Boruma" --out "<the game's mod folder>"
```

This writes `zz_ref_987_10_27/` and `zz_ref_987_10_27.mod`. The bookmark it adds is:

```
bm_987_10_27 = {
	start_date = 987.10.27
	is_playable = yes
	weight = {
		value = 0
	}
	character = {
		name = bookmark_ref_987_10_27_900
		history_id = 900
		title = d_munster
		culture = irish
		religion = insular_celtic
		government = feudal_government
		difficulty = "BOOKMARK_CHARACTER_DIFFICULTY_MEDIUM"
		birth = 941.1.1
		type = male
		dynasty_house = house_british_isles_briain
		dynasty_splendor_level = 1
		position = { 400 300 }
	}
}
```

## A reference from another date

The new-map rules copy the new regions' world from the reference as it is: who rules each title, who is alive, who is married to whom, what each court holds. A reference from another date brings that world from the wrong moment into your campaign: rulers who in your campaign's year are long dead or not yet born, titles held by the wrong generation, families that do not fit your date. Nothing refuses such a reference, because the tool cannot tell which date you meant. The tool still keeps your own campaign's land and people as they are, so the damage is limited to the copied regions; but they would not be the world of your date.

For the religion rules alone, the date matters less: they copy the faiths, rites and religious organizations, which change little from one date to another.
