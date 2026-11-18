# Old game files: what the tool carries, and how to fetch the rest

`ck3update` brings an old save forward with only the game you have installed, plus a reference save made in that game. To do that it needs to know a little about older versions: their maps, face genes and a few counts. Most of that ships inside the tool. This page says what ships, when you might still want an older build's files, and how to get them.

## What ships with the tool

These are definition files and counts only, never a whole old game and never a save. About 0.9 MB in all.

| Folder | What it holds | Used for |
|---|---|---|
| `known_titles/vanilla_1.8.2` | the 1.8.2 map: title keys, their nesting, each barony's province | settling titles a newer map removed or moved |
| `known_genes/` | face gene tables for vanilla 1.8.2 and older portrait-mod builds | reading old faces without the old game or mod |
| `baselines/1.20.1.2`, `baselines/1.21.0` | which fields each kind of entry carries | lint's field check |
| `known_slots/1.20.1.2.json` | building slots per province in a fresh 1.20 game | rows copied from a 1.21 reference into a save on its way through 1.20 |

## When an older build's files still help

For the usual cases you need nothing extra. A 1.20 save, or a 1.8 save with a reference made in your current game, works with what ships.

An older build's `game` folder helps in two cases:

- **A save from a version whose map the tool does not carry,** between 1.9 and 1.19. Give that version's `game` folder with `--old-game-dir`, so removed and moved titles are settled from its own map.
- **Old faces from a portrait-mod build the tool does not carry.** Use `--old-portrait-mods` with that build.

You need only the definition files (`game/common`, `game/history`, `game/gfx/portraits/...` for genes), not the whole game.

## Getting an older build's files

### With Steam's Betas tab

In Steam, open Crusader Kings III, then Properties, then Betas, and pick the previous version if it is offered. Steam downloads that build in place of your current one. Copy the `game` folder somewhere else, then switch back to the current version.

This is simple, but it replaces your installed game while you do it.

### With DepotDownloader

[DepotDownloader](https://github.com/SteamRE/DepotDownloader) downloads a specific build's files from Steam without touching your installed game. You need your own Steam login, and must own the game.

- **App** 1158310, **main content depot** 1158311.
- **Use an explicit manifest id** (`-depot 1158311 -manifest <id>`), not only `-branch`. With `-branch`, DepotDownloader quietly falls back to the current build's files for any depot that has no such branch, and mixes versions without saying so. Manifest ids per version are listed on SteamDB's depot history page. For example, 1.20.1.2's main content is manifest `2013027804061508407`.
- **Fetch definitions only** with `-filelist`, a text file of path patterns such as `regex:game/common/.*` and `regex:game/history/.*`. That is a few hundred MB instead of the whole game.
- **Check the download** against its manifest. Run DepotDownloader once with `-manifest-only` to get the manifest's file list, hash the downloaded files, then run:

  ```
  python scripts/verify_depot_download.py <manifests folder> <hashes.csv> 1158311:<manifest id>
  ```

  It reports every file missing, the wrong size, or the wrong SHA-1.

Then point the tool at it, for example `ck3update update <save> --old-game-dir <download>/game`.
