# What the updater does for a 1.8 save that the game alone can't

A save from Crusader Kings III 1.8 can't be opened in 1.20 directly. The game crashes while loading it, at the step "Setup powerful vassals", in 1.19 and 1.20 alike. Versions 1.14, 1.16 and 1.18 still load it. So with the game alone, a player has to install old versions from Steam's beta branches and step through them: open the save in 1.18, save it, open that in 1.19, save it, and so on.

The updater brings a 1.8 save to 1.20 in one step. This page compares the two routes on the same campaign. One route is the game alone, stepping 1.8.1 to 1.18.4 to 1.19.0 to 1.20.1.2 with each version saving the last one's save. The other is the updater's output, after the 1.20 game has loaded and saved it.

Both routes ran on this project's founding campaign (a 1.8.1 game started in 987), with mods turned off for the game-alone route. That matters for one part of this page: what comes from mods (a custom faith, portrait mods) can't be compared, because the game-alone route never had them loaded.

Of everything in the save, about 97% comes through both routes the same way, matched entry by entry. The rest is below.

## What the game does itself, and the updater does in one step

Much of the updater's 1.8 work does what the game's own versions would have done on the way. Its value there is saving you the stepping stones, not doing something the game can't.

- **The newer save format.** Each version between 1.8 and 1.20 changed how some things are written, and the game rewrites or accepts them as it steps. The updater rewrites them directly ([format rules](rules.md)).
- **The map.** 1.18 redrew parts of the map. The game-alone route ends with the same 3,476 counties as a new 1.20 game, and so does the updater's.

## What the game converts, but gets wrong

- **Plots that never move again.** The game-alone route carries every scheme, but all 1,334 of the founding campaign's schemes keep a marker the old game wrote, which 1.20 reads as "frozen". They never progress again. The updater clears it, so your plots move ([R29](rules.md)).
- **Religion flattened.** The game maps the old faiths onto 1.20's, but it gives every Ash'ari and Maturidi character one Hanafi rite, across 64 cultures and 744 provinces. The updater keeps each school apart ([R8, R9](rules.md)).
- **Characters without a rite.** The game-alone route leaves 8,292 living characters with no rite at all, a state a new 1.20 game never has. They are the characters who had no faith of their own in 1.8. The updater gives each the rite they belong to ([R12](rules.md)).
- **Old faiths kept.** 1.20 reorganized religion into faiths and rites, and some 1.8 faiths became rites of a larger faith. The game-alone route keeps 46 of the old faiths by name anyway, such as Ash'ari, Ismaili, Coptic and Ibadi, though a new 1.20 game has none of them. The updater's output has exactly a new 1.20 game's 103 faiths, plus your custom faith ([R8, R9](rules.md)).

## What the game loses, and the updater keeps

- **Faces.** The game-alone route keeps the stored face of 99 characters out of 83,376. Everyone else gets a newly generated face, so nearly every portrait in your campaign changes. The updater keeps each character's face ([R19](rules.md)).
- **The regions new on the 1.20 map.** The game-alone route has the new counties, but not the cultures and people a new 1.20 game puts there. The updater brings in 55 cultures and 7,853 characters from a 1.20 reference game for those regions, so they are ruled and peopled as in a new game ([R14 to R17](rules.md)).
- **What 1.20 added and an old save never had.** After its own 1.20 load and save, the game-alone route still lacks several things a new 1.20 game has. The updater's output has them:
  - homes for landless characters (458 domiciles);
  - the church's clerical regions (52);
  - the groups the game's situations track (55);
  - vassal contracts in 1.20's form (583 more of them);
  - the title details 1.20 keeps, such as clerical electors, men-at-arms ownership and treasury budgets.
- **The innovation a culture is picking up.** 1.20 drops that marker when it loads an old save, so the culture forgets which innovation it was learning. The updater moves it to the form 1.20 reads ([R26](rules.md)).
- **Gunpowder.** A culture can only research the innovations it lists. On the game-alone route no culture lists gunpowder, so none can ever research it. The updater's cultures list gunpowder, with the same discoveries as the game-alone route. The game alone also leaves out three innovations added after 1.8 on most of the campaign's cultures: Pole Vault (228 cultures), and Legacy of Persia's fritware and mural sextant (229). A new 1.20 game lists all three on every culture. Since 0.6.49 the updater lists every innovation a new 1.20 game lists on every culture ([R49](rules.md)).
- **Nicknames' own text.** The updater's output keeps 259 characters' nickname texts. The game-alone route has none ([R23](rules.md)).
- **Regiments and artifact effects whose names changed.** The game-alone route deletes them: the campaign's 11 Teutonic Knights regiments, 25 Chu-ko-nu regiments and the Hawk of Quraysh's effects are gone. The updater renames them to what replaced them: Order Serjeants, Shenbigong, and the corrected Hawk of Quraysh ([R25](rules.md)).
- **House feuds.** 1.20 no longer runs the old feud story. On the game-alone route both of the campaign's feuds are simply forgotten. The updater keeps them as feuds between the houses, which last until the houses reconcile in play ([R27](rules.md)).
- **Marriages rejected from the marriage bed.** 1.20 dropped that character bonus. On the game-alone route, the 47 characters who had it lose it, and their marriages can have children again. The updater marks each such marriage the way 1.20 does instead, so it stays childless ([R28](rules.md)).
- **Artifact pictures, armour models and coat-of-arms patterns.** 1.20 renamed some of the files a save points at. The game-alone route keeps the old names, so they point at files that no longer exist. On the founding campaign that is 16 artifact pictures (Excalibur's among them), 460 armour models and 31 coat-of-arms patterns, which show nothing. The updater points each at the file's new name ([R30](rules.md)).

## Not part of the comparison

- **Your mods.** A custom faith from a mod (this project's own campaign uses Way of Scarcity) is carried by the updater ([R10](rules.md)). The game-alone route ran without mods, so it can't show what the game would do with it.
- **Repairs for edited saves.** Some patches fix states that only a hand-edited save has, such as a ruler left without a contract ([R31](rules.md)). They are not about the version gap.

## What neither carries

Some things later versions removed have no place in 1.20. They are listed on [what is not carried over](not-carried-over.md). Where the updater deliberately does something other than the game's own conversion (who gets the land in a redrawn county, for instance), [differences from the game](differences-from-the-game.md) explains each choice.
