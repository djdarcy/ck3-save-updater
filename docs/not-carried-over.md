# What doesn't carry over

Some things in an old save have no home in the current game. The game removed them, and nothing took their place. The update leaves them out, and the game drops them when the save loads. This page lists them, so you can see what your campaign loses.

Miss something here? Say so in [GitHub Discussions](https://github.com/djdarcy/ck3-save-updater/discussions). We are collecting these for a separate mod that brings back mechanics older versions had. The updater itself only uses what the base game defines.

## Timed modifiers from removed events

These modifiers came from events that later versions removed or rewrote. Most of them last a few years and then expire anyway. Version 1.13 reworked holding court, and most of these went with it.

We checked each one against every modifier 1.20.1.2 defines, by name, description and effect. None has a successor. A few have a cousin with the same idea but different numbers or a different story. Where you agreed a cousin fits, the update uses it (see "Mapped to a cousin" below).

| In game | What it did | Removed in | Count in the founding campaign |
|---|---|---|---|
| Weapons Ban in Cities | faster county control growth, a little safer travel | 1.13 | 19 counties |
| Open Weapon Carry Permitted | +10 county opinion, a little more dangerous travel | 1.13 | 1 county |
| Imprisoned Frontier Hero | −20 county opinion, slower levy reinforcement | 1.13 | 16 counties |
| Honored Frontier Hero | +20 county opinion, faster levy reinforcement | 1.13 | 1 county |
| Foreign Guards | +2 prowess, +5% levies | 1.9 | 14 characters |
| Got Lost | −1 health | 1.9 | 11 characters |
| Tax Revolt Ongoing | −40 county opinion | 1.13 | 5 counties |
| Tax Assessor | +25% vassal tax | 1.13 | 1 character |
| Dancing Mania: The Divine | +15 county opinion | 1.13 | 4 counties |
| Monsters in the Wilderness | −25 county opinion, more dangerous travel | 1.13 | 3 counties |
| Roaming Beasts | +5 county opinion, more dangerous travel | 1.13 | 2 counties |
| Monster Killed | +15 county opinion, safer travel | 1.13 | 2 counties |
| Smelly Court | −10 vassal opinion, less dread gained, −2 court grandeur | 1.13 | 2 characters |
| Inhospitable Host | −2 court grandeur | 1.13 | 1 character |
| Spying Holes | +5% chance to discover schemes | 1.13 | 1 character |
| Secret Escape Passage | enemy hostile schemes 15% less likely to succeed | 1.13 | 1 character |
| Failed Deception | −1 intrigue, weaker hostile schemes | 1.13 | 1 character |
| Civic Admiration | +10% tax from republics | 1.13 | 1 character |
| Favored Town | +20 county opinion, faster development | 1.13 | 1 county |
| Popular Justice | +25 county opinion, faster county control growth | 1.13 | 1 county |
| Punished Troublemakers | knights 10% less effective | 1.13 | 1 character |
| Archers Insight | archers 15% stronger and tougher | 1.9 | 1 character |
| Hostile to Different Cultures | −10 opinion from other cultures, +5 from your own | 1.13 | 1 character |

## Mapped to a cousin

These had no exact successor, but the current game has the same idea. The update uses the current one.

- **Tax Relief** from a hold court becomes the current game's own "Tax Relief". It is stronger, with half the tax and more opinion. The old one also slowed development.
- **Rice Fields** becomes "Agricultural Innovation". The same Iberian event gives it, with the same effect.
- **Rejected From Marriage Bed** becomes a hidden "no children" relation between the two spouses. The current game's own events check that relation instead.

## Artifact bonuses the current game has no step for

The current game keeps fewer steps for some artifact bonuses. The update moves each one to the nearest step the game keeps.

- **Building cost.** Older artifacts went from −1% to −8%. The current game keeps −1% to −4%. A stronger bonus becomes several of those added together, so −7% becomes −4% and −3%, and the total is the same.
- **Opinion with all vassals.** The current game has no plain artifact bonus for this. +1 becomes the game's own +1 all-vassal bonus. +3 becomes its exact +3, which also gives a little prestige. +4 becomes +5. +2 becomes a pair, +5 and −3, which adds up to +2 and shows as two lines in the artifact's tooltip.

## Scheme agents without a position

Plots in older saves could have any number of agents. The current game gives each kind of plot a fixed set of agent positions, and some plots none at all. The update seats each plot's agents in its positions, strongest first. Agents beyond those positions leave the plot. So do agents in plots the current game gives no positions, such as converting someone to witchcraft.
