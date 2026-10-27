# New-map regions

Crusader Kings III 1.20 reworked the map. It added about 3,600 provinces and 5,700 titles that a 1.8-era save has never heard of (East and Southeast Asia, Tibet, Japan, ...), removed some titles the old map had, and redrew some county borders. Loaded as it is, an old save leaves every new title unheld, and the game hands them to the player. The new-map rules bring those regions in, held and populated, from a save written by 1.20 at your campaign's date. They are opt-in and still in progress.

## Turning it on

```bash
ck3-save-migrator migrate "My_Old_Campaign.ck3" --rules all,R15,R14,R16 \
    --reference "A_1_20_Game_At_My_Campaign_Date.ck3" --old-game-dir "Old_CK3/game" \
    -o "My_Old_Campaign.migrated.ck3" --report "My_Old_Campaign.report.json"
```

- `--reference` is a save written by 1.20. Start a 1.20 game at your campaign's date and save it: the new regions' rulers, courts and families are copied from it as they are on that date, so a reference at another date brings in the wrong generation.
- `--old-game-dir` is the `game` folder of the version your save was made with. R15 reads its map to find what the 1.20 map calls the land of titles it no longer has. Without it R15 does nothing and says so.
- The current game's folder is found automatically, or given with `--game-dir`.
- The religion rules (R8 and the others in `all`) must run too: a copied person's faith has to point at something. A selection without them is refused. See [Rules](rules.md#prerequisites).

## The rules

- **R15 (dead-titles)** settles the save's titles that 1.20 removed or moved, before anything is copied.
- **R14 (new-titles)** plans every title and province of the reference that your save does not have. Runtime-created titles (keys starting with `x_`) are not copied.
- **R16 (people)** plans the people those titles need: their holders, the holders' courtiers, and the close family of both (spouses, children, father and parents), living or dead.
- **R17 (transplant-write)** writes everything the three planned in one pass. It runs by itself whenever R14, R15 or R16 is chosen. Planning first and writing once is what lets every link be checked: a link is kept only when what it points at is in the output.

What R16 brings along goes beyond the people themselves: their houses, dynasties and cultures, coats of arms, council tasks, court positions, vassal contracts, memories, artifacts, men-at-arms regiments, the relations and opinions among them, and their queued events. The new regions also get every culture 1.20 added, the mercenary companies a fresh 1.20 game has (with their titles and regiments), and China's situations (the dynastic cycle, with its regions and groups). Holy sites of the new regions (Angkor, Borobudur, Samarkand, ...) are attached to their places again once those places exist.

## How things are matched

Every copied object gets a new number that cannot clash with anything in your save, and everything it points at keeps pointing at the right thing. The game numbers its objects by slot, and the copied ones take free slots above your save's own. `lint` reports two objects of the same kind sharing a number, which the game cannot load.

Where your save already has the same thing, the copy points at yours instead of bringing a second one:

- titles, by their key (`k_france`), except runtime-created `x_` titles, whose keys are reused numbers rather than identities;
- cultures, by the culture they were made from;
- historical characters, by their history id;
- dynasties and houses, by their history key.

A match only redirects the reference's links to your object; nothing from the reference is written into it. People alive in 1.20's history but dead in your campaign stay exactly as your campaign has them. A ruler of 1.20's history whose land your campaign already holds comes in without land, at the court of the one who holds it. A copied title whose runtime name your campaign already uses is renumbered, so no name points at two titles. Links to things that are not brought along are removed rather than left pointing at nothing.

Your campaign's own titles keep their structure. A new title is added under an existing one where 1.20's map puts it there, and nothing of your realm is given to a copied ruler. Titles left without a de jure parent, because the title above them in 1.8.1 is gone, get the parent 1.20's map gives them.

The copied cultures, history dynasties and history houses are added to the game's start-of-game lists, and copied coats of arms keep their names; a name your campaign already has keeps your campaign's coat.

## Titles the new map removed or moved

R15 settles each title your save has that 1.20 no longer defines, and each barony 1.20 moved to another province, by place: what the 1.20 map calls the land the title covered.

- A barony's successor is the 1.20 barony on its old province; if there is none, the province is wasteland.
- A county's or higher title's successors are the 1.20 titles one tier up from its old de jure children's successors.
- A title 1.20 defines only under another tier's prefix (for example `e_india` becoming `h_india`) is matched by its key.
- A barony 1.20 moved to another province keeps its place on the map and takes the name 1.20 gives that place.

A match is clean when it has exactly one successor, that successor covers the same land under the 1.20 map, no other title matches the same successor, and the save does not already have that key. Where the match is clean, your title takes the 1.20 name and stays with its holder. Otherwise (1.20 split or redrew the land, the land is wasteland, or there is no successor) your title is removed with every link to it, and the 1.20 titles for that land come in through R14 with their rulers. A county's record (its culture, faith and development) follows: a renamed county keeps its record under the new name, and a removed county's record is dropped.

A save that is already at the current version leaves R15 nothing to do, so migrating a migrated save does not undo the first migration.

## Baronies in redrawn counties

1.20 redrew county borders, so some of your campaign's baronies now belong to a different county than they did. Left alone, the game re-seats each one under its new county when it loads and gives it to that county's holder, or to no one. The tool settles them first.

A moved barony belongs to its 1.20 county, and its baron keeps it as a vassal of the new county's holder. Some cases the game's own rules do not allow, and these are left to the game and listed in the report with the reason:

- a barony whose count also holds land outside its new county (one person cannot have two lieges);
- a barony that is the capital of its new county (a county's holder always holds its capital);
- a new barony of a copied ruler inside one of your counties, which goes to your count.

Where 1.20 drew a new county around baronies your campaign held, that county goes to your campaign rather than to the ruler 1.20's history gave it:

- a baron of the player's family (the player's house or dynasty, or a spouse's) is promoted to count of it;
- otherwise the count who held those baronies in your campaign takes the new county, and his barons stay his vassals;
- barons whom 1.20's history put in the county keep their baronies, as vassals of the new count;
- the ruler who loses the county keeps the rest of his lands; one left with nothing joins the new count's court;
- a baron whose barony is the capital of the new county, when someone else becomes its count, gives the barony to the new count and joins his court (none of these counties has a built barony free).

New-map baronies on provinces the old map had left empty arrive with their 1.20 holding, buildings and garrison. Provinces of your own that your campaign never built stay as they were and are counted in the report.

## Monastic orders

The 1.20 monastic orders that hold land in the old world are added as the new version has them, with their leases on your land, and listed in the report as expansion content. `--no-expansion-orders` leaves them out.

## The report

Every change is listed in the `--report` JSON: the titles and provinces planned, the people brought in and the rulers displaced, each title R15 renamed or removed and what happened to its land, every barony re-parented, settled or left to the game, the empty provinces filled, the expansion orders and leases added, and the links dropped. `-v` prints a one-line summary per rule. See [Reports](reports.md).
