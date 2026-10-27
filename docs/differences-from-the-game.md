# Differences from the game

When the current game loads a save from an older version, it converts what it can by itself. In a few places the tool deliberately does something else, so that the campaign comes through as it was played. This page lists those places; the [CHANGELOG](../CHANGELOG.md) has the detail for each version.

## It keeps the campaign's land

- **New titles.** Loaded as it is, an old save leaves every title 1.20's map added unheld, and the game hands them to the player. With the new-map rules, those titles arrive with the rulers a 1.20 game at the campaign's date gives them, and nothing of the campaign's realm is given to a copied ruler. See [New-map regions](new-map-regions.md).
- **Baronies in redrawn counties.** 1.20 redrew county borders. The game re-seats each moved barony under its new county when it loads and gives it to that county's holder, or to no one. The tool moves the barony to its new county and lets its baron keep it, as a vassal of the new county's holder. Where the game's own rules do not allow that, the barony is left to the game and the report names it with the reason.
- **Counties drawn around the campaign's baronies.** Where 1.20 drew a new county around baronies the campaign held, the county goes to the campaign (to a baron of the player's family, or else to the count who held those baronies) rather than to the ruler 1.20's history gave it.
- **Titles the new map removed or moved.** Each is matched to what 1.20 calls the same land. Where the match is clean, the title takes the 1.20 name and stays with its holder; otherwise the 1.20 titles and their rulers take the land, and the report lists each case.
- **Empty provinces.** New-map baronies on provinces the old map had left empty arrive with their 1.20 holding, buildings and garrison, instead of losing their holders on load.

## It carries what the game drops

- **The new regions' rulers and people**, with their courts, close families, houses, cultures, men-at-arms, relations, opinions and queued events.
- **Mercenary companies**: the new regions get the companies a fresh 1.20 game has, with their titles and regiments.
- **Monastic orders**: the 1.20 orders that hold land in the old world are added as the new version has them, and listed in the report as expansion content. `--no-expansion-orders` leaves them out.
- **County records**: every county the tool brings in gets its record (culture, faith or rite, development), which the game reads for epidemics, buildings and tournaments. Without it the game's error log fills with "culture trigger [Failed context switch]" within a minute of play.
- **China's situations** (the dynastic cycle) and every culture 1.20 added.

## It keeps the campaign's religion

- **Catholicism and Orthodoxy** stay independent faiths, each with its religious head carried over, as the campaign had them.
- **Custom faiths** are carried with their doctrines, fervor, religious head, holy sites, founder and history, as a faith of their own or as a rite of the faith their template now belongs to.
- **Sunni schools.** 1.20 has no rite for the four old Sunni theological schools. The game's own conversion of an old save gives every Ash'ari and Maturidi character the same rite (Hanafi), whatever their school; the tool assigns by school instead. It gives each the nearest 1.20 school of law: Ash'ari becomes Shafi'i, Maturidi and Mu'tazila become Hanafi, and Muwalladi becomes Maliki.
