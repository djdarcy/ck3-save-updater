# The reference save

Several rules copy what they need from a save written by the current game: the religion rules (R8 to R12) rebuild religion from it, and the new-map rules (R14 to R16) bring in the regions 1.20 added, with their rulers, courts and families. That save is the reference, passed to `migrate` as `--reference`.

For religion, any 1.20 save will do; one at the same start date is closest. For the new-map regions it matters much more: the reference should be a fresh 1.20 game started on your campaign's own date. The new regions' people are copied as they are in the reference, so the reference has to show the world at the same moment as your campaign.

## Why a mod is needed

The game starts new games only on its bookmark dates. Unless your campaign happens to be on one of them, there is no way to start a 1.20 game on its date from the menu. The way around it is a small local mod that adds one bookmark on your date. `ck3update reference-mod` writes that mod for you.

## Steps

1. **Find your campaign's date**: the in-game date of the save you will update (shown when you pick it on the game's load screen). The save also records it as `meta_date` in its metadata block, which is plain text at the start of the `.ck3` file.
2. **Choose a ruler for the bookmark.** A bookmark has to name a playable character: someone alive on your date who holds a title then. Look in the game's own files, inside the game's `game` folder: `history/characters` gives each historical character's history id, birth date, culture, faith and dynasty house; `history/titles` gives who holds each title from which date. Pick a ruler whose title is theirs on your date. Their government must suit that title (most are `feudal_government`; pass `--government` otherwise).
3. **Write the mod** into the game's `mod` folder (in your documents folder, under `Paradox Interactive/Crusader Kings III/mod`):

   ```bash
   ck3update reference-mod --date <your date> --character <history id> --title <title key> --culture <culture key> --religion <faith key> --house <dynasty house key> --birth <birth date> --name "<the ruler's name>" --out "<the game's mod folder>"
   ```

   It writes a folder `zz_ref_<date>` (holding `descriptor.mod`, the bookmark and its English text) and, beside it, `zz_ref_<date>.mod`, which the launcher reads. It refuses to overwrite either if it already exists. Add `--female` for a female ruler.
4. **Enable the mod** in the game's launcher, in a playset with nothing else that changes bookmarks.
5. **Start a new game** from the bookmark named "`<date>` Reference (ck3update)", with any character, and **save at once**, before unpausing, so the world is exactly as the game starts it on that date.
6. **Pass that save** to `migrate`:

   ```bash
   ck3update migrate "My_Old_Campaign.ck3" --rules all,R15,R14,R16 --reference "My_1_20_Reference.ck3" --old-game-dir "Old_CK3/game"
   ```

Disable the mod again for your normal games; it only adds a bookmark.

## Example: 27 October 987

Brian Boruma (history id 900) holds the duchy of Munster (`d_munster`) from 978.7.1, and the Irish titles are feudal from 935.1.1 (the game's `history/titles/k_ireland.txt`). He was born on 941.1.1, is Irish, of the insular Celtic faith and of the house of Briain:

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
