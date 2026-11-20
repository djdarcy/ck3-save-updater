# What changed in 1.21, and why

Version 1.21 ("Florin", released with Silk & Silver in November 2026) rebuilt the game's economy. A new game explains the new systems with tutorials and advice. A campaign brought over from 1.20 gets none of that, so the changes can feel like complexity for its own sake. This page explains them.

For each topic it gives three things side by side:
- **What Paradox said** they wanted, from their development diaries and the patch notes.
- **What we see** in the game's files and in saves.
- **How the two compare.** Where they differ, we say so, and what kind of difference it seems to be: a likely bug, a deliberate change of course, an aim that was dropped, or one we can't judge yet.

Neither layer is the final word. A designer's aim and what ships can differ, and both help explain how the game behaves.

## 1. The aim

- **Said.** The patch notes give the aim as reducing "easy gold flow" and adding "long term planning, choice, realism and specialization". The first development diary speaks of slowing the snowballing economy, and of bringing player and AI economies closer.
- **Seen.** Most flat bonuses to income are gone. In their place, nearly every effect depends on where it is: what the county can produce, whether it is a capital, who holds the duchy. We'd describe it as an economy of places and goods. Geography decides what a place can become, and the player chooses within that.
- **Compare.** The two describe the same direction from different ends. Whether the economy actually snowballs less in play is not something we have measured. A converted campaign earns less at first, but that comes from what the conversion loses (below), so it says nothing about the aim either way.

## 2. Districts instead of building slots

- **Said.** Holdings are now built from districts, with buildings inside them. The patch notes say the change brings more diversification and a better reflection of the medieval world. The diaries describe a district as a long-term investment, harder to switch than a building.
- **Seen.** Every holding has a holding district (its castle, city or temple line), one resource district, and regular districts by size. The game's own conversion of a 1.20 campaign leaves every regular district empty. On this project's founding campaign, 19,569 buildings became none.
- **Compare.** They differ for old saves. The patch notes describe a new game's start, with holding districts built and levelled and a resource district in every county capital. A converted save starts with nothing built. Nothing says old saves are meant to start empty. **Kind:** most likely the converter was left simple, but we can't yet tell whether that was a choice. The updater fills the districts from your old buildings ([what the updater repairs](what-the-tool-adds-1.20-to-1.21.md)).

## 3. Settlement size and district slots

- **Said.** Development is split into settlement size (1 to 10) and prosperity. Size is the way to more district slots, and it also lowers control and popular opinion, so big cities take more work.
- **Seen.** A new game sets sizes from history, so Rome and Constantinople start large. The conversion sets every province of an old save to size 1.
- **Compare.** By Paradox's own slot rule, a converted campaign has the fewest slots everywhere, its greatest cities included. **Kind:** likely a simplification in the converter; bug or choice can't be told yet. The updater raises each province to the size a new game gives it ([R40](rules.md)).

## 4. Prosperity and food

- **Said.** Prosperity takes over development's old economic role: taxes, supply, innovation and prices. Every holding needs food by its size, from cereals and meat. Without it, the holding shrinks and its people grow unhappy.
- **Seen.** A converted save's development becomes its prosperity exactly. But its empty districts produce little, so a carried campaign has about half a new game's production after seven months.
- **Compare.** No difference of aim. The low production follows from the empty districts in topic 2. For a player it means food can run short sooner than in a new game, until the districts are rebuilt.

## 5. Markets and goods

- **Said.** There are 44 trade goods, 16 of them basic. Every de jure duchy with a county gets a market, 922 on the current map. When an older save loads, its markets are created on load.
- **Seen.** The conversion creates the markets with nothing in them, and they fill once time runs. The founding campaign has 902 markets, not 922.
- **Compare.** They agree that markets are made on load. The 20 missing markets are not traced yet. 1.21 added new de jure duchies in several regions, so a converted save may keep the old set. **Kind:** can't tell yet; possibly a converter omission.

## 6. Routes and roads

- **Said.** Dukes and above can run distribution routes for staple goods. Roads grow from tier 0 to 5 with use. The patch notes say an unused road drops a tier every 4 years; a development diary said every 24 months.
- **Seen.** The game's own file sets it at 48 months, so the patch notes are right. A converted save gets no roads at all, where a new game has about 4,200.
- **Compare.** Paradox gives no reason for roads beyond trade. What we see suggests roads record past trade, so a converted world, with no trade history in the new system, has none. Whether that is intended for old saves, we can't tell. The diary's 24 months was changed before release, or was simply wrong. The updater brings in a new game's roads ([R34, R36](rules.md)).

## 7. Buildings and income

- **Said.** General tax multipliers are gone. A building may need goods, and when its need isn't met, its bonus doesn't apply. Tax is split into ten types (agricultural, mining, urban, artisan, commerce and others), each scaling with size.
- **Seen.** 1.21's buildings carry no flat monthly income and no development. Their value comes through production and specific tax types.
- **Compare.** The files match what was said. How needs behave in play we haven't measured. For a player: a building that looks weak may be starved of a good, not badly chosen.

## 8. Choosing what a place becomes

- **Said.** The player shapes a holding: rural districts suit small places, a player can hold back a holding's growth, and replacing a resource district costs the buildings inside it.
- **Seen.** The files narrow the choice before the player makes it. A county can make only the trade goods it has potential for; the patch notes put that at 3 to 5 per county. A duchy-capital district needs the duchy's capital barony, and its holder holding the duchy. Slots are few.
- **Compare.** The choice is real, but geography and titles set its limits first. **Kind:** a deliberate design detail, not a change of aim. The updater asks you only where a real choice exists: where your old save and the new game put different resource districts in one province (see `--auto` in [updating a save](updating-a-save.md)).

## 9. Innovations

- **Said.** New innovations were added in every era for the new economy, and districts unlock from many of them. Innovations no longer add building slots, and holding levels unlock by era instead.
- **Seen.** A converted campaign's cultures never list 25 innovations a new game has. Most are on the patch notes' list, such as heavy plow, coppicing, prospecting and monasticism. Five are not named there: Public Works, Communal Government, Urbanization, Renaissance Thought and Pole Vault. A culture can't research what it doesn't list, so some district levels can never be reached.
- **Compare.** Spreading unlocks across many innovations only works if every culture can reach them. A new game lists them all; the conversion doesn't add them, and nothing says old saves should differ. It has happened before: the game's own conversion has left new innovations unlisted twice, gunpowder in 1.20 and these 25 in 1.21. **Kind:** a recurring omission in the converter. We think it is worth reporting to Paradox. The updater adds them ([R47](rules.md)).

## Three things Paradox changed on purpose

The patch notes name these, so they are deliberate changes of course, and the updater doesn't try to carry them:
- development bonuses from traits, lifestyle focuses and holy sites were not moved to prosperity;
- innovations no longer add building slots;
- artifacts no longer give tax bonuses.

## In your carried campaign: what to open first

- **A holding's view.** See its districts: the holding district, the resource district, the regular districts and, in a duchy's capital, the duchy-capital district. The updater has filled them from your old buildings where 1.21 allows.
- **Your capital's market.** Its goods, surplus and deficit tell you what your realm lacks. Food first.
- **A province's size and prosperity.** Size decides how many districts fit. Prosperity drives income.
- **The buildings 1.21 had no place for.** They are listed on [what is not carried over](not-carried-over.md).

## Sources

- Paradox Interactive, the 1.21 patch notes, as kept on the CK3 wiki: https://ck3.paradoxwikis.com/Patch_1.21 (read 2026-11-20).
- Paradox Interactive, Silk & Silver development diaries, posted as Steam announcements for Crusader Kings III (https://store.steampowered.com/news/app/1158310):
  - 1, "The Vision of Silk & Silver" (2026-04-21);
  - 2, "Trade Vision" (2026-05-12);
  - 5, "Iteration" (2026-09-01);
  - 6, "Merchants, Republics, & the Silk Road" (2026-09-15);
  - 8, "Trade in Practice" (2026-10-27);
  - 9, "3D Art, Music, Modding" (2026-11-03);
  - and the release post (2026-11-17).
- The game's own files (version 1.21.0): `common/defines/00_defines.txt` (roads), `common/culture/innovations` (innovations), `common/scripted_triggers` (duchy-capital rule).
- This project's measurements on its founding campaign, summarized in [what the updater repairs after 1.21's own conversion](what-the-tool-adds-1.20-to-1.21.md).
