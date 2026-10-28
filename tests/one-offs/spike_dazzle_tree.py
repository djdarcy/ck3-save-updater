"""spike_dazzle_tree: can CK3 patch packs and patches live in dazzlecmd-lib's tree (epic #14, first-mile 2026-10-27,
DWP 2026-10-27__14-21-50__dev-workflow-process__patch-toml-contract.md, unit 1).

Questions, each with its prediction written before the run:
  Q1 A pack declared as a kit is discovered, and `kit disable` / `kit enable` round-trip through the config.
     Prediction: yes (kits are the activation axis's only level, verb_axis.py VERB_AXES applies_at={KIT}).
  Q2 A tree extension can graft one node per patch under the pack, with card fields (title, issue, kind), and every
     surface sees it (build_engine_tree).  Prediction: yes (instance_plane grafts kits and tools the same way).
  Q3 A single patch can be disabled through the lib's own activation verb.
     Prediction: NO -- activation applies at kit level only; a patch needs either an upstream widening of
     applies_at (named in verb_axis.py as "later B1 slices") or the tool's own disabled list.
  Q4 The fallback for Q3: the engine's property store holds `<patch node>.activation = inactive` and reads it back.
     Prediction: yes.
Control arm (designed to fail): ActivationContext.disable on a name that is not a kit must NOT write disabled_kits;
if it does, the lib accepts anything and Q1's pass proves nothing about kit identity.

Isolation: config_dir and DAZZLECMD_CONFIG point into a temp folder; nothing under the home folder is written
(checked at the end: ~/.ckupdater must not exist after the run if it did not before).

Usage: python -I tests/one-offs/spike_dazzle_tree.py
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
from pathlib import Path

PACK = "ck3_1_20"
PATCHES = [("r1-converging", "Drop converging from temporary opinions", "declarative"),
           ("r5-empty-keys", "Delete entries whose key is empty", "declarative"),
           ("r17-transplant", "Write the transplanted titles", "script")]


def build_project(root: Path):
    (root / "kits").mkdir()
    (root / "kits" / f"{PACK}.kit.json").write_text(json.dumps({
        "name": PACK, "version": "0.1.0", "description": "Patches from 1.8-1.19 saves to 1.20",
        "always_active": False, "tools_dir": "tools", "manifest": ".ckupdater.json", "tools": []}), encoding="utf-8")
    (root / "tools").mkdir()
    for pid, title, kind in PATCHES:
        d = root / "patches" / PACK / pid
        d.mkdir(parents=True)
        (d / "patch.toml").write_text(f'format = 1\nid = "{pid}"\ntitle = "{title}"\nkind = "{kind}"\n',
                                      encoding="utf-8")


def graft_patches(engine, tree):
    """The tree extension under test: one node per patch folder, under the pack's node."""
    import tomllib
    root = Path(engine.project_root)
    for pack_dir in sorted((root / "patches").iterdir()):
        pack_key = f"{engine.command}:{pack_dir.name}"
        if pack_key not in tree:
            tree.add_node(pack_key, obj=None, kind="pack", level="kit")
            tree.add_edge(engine.command, pack_key)
        for pdir in sorted(pack_dir.iterdir()):
            meta = tomllib.loads((pdir / "patch.toml").read_text(encoding="utf-8"))
            key = f"{pack_key}:{meta['id']}"
            tree.add_node(key, obj=None, kind="patch", level="patch", title=meta["title"],
                          patch_kind=meta["kind"], path=str(pdir))
            tree.add_edge(pack_key, key)


def main():
    home_cfg = Path.home() / ".ckupdater"
    home_before = home_cfg.exists()
    results = {}
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        proj, cfg = tmp / "proj", tmp / "cfg"
        proj.mkdir()
        cfg.mkdir()
        os.environ["DAZZLECMD_CONFIG"] = str(cfg / "config.json")
        build_project(proj)
        from dazzlecmd_lib import AggregatorEngine
        from dazzlecmd_lib.contexts import ActivationContext
        from dazzlecmd_lib.fqcn_tree import build_engine_tree
        engine = AggregatorEngine(name="ckupdater", command="ckupdater", tools_dir="tools", kits_dir="kits",
                                  manifest=".ckupdater.json", config_dir=str(cfg), project_root=str(proj))
        with contextlib.redirect_stdout(io.StringIO()):
            engine.discover()
        kit_names = [getattr(k, "name", None) for k in (engine.kits or [])]
        results["Q1 discovered"] = PACK in kit_names
        act = ActivationContext(engine)

        def disabled():
            return list(engine._get_config_list("disabled_kits", default=[]) or [])

        try:
            act.disable(PACK)
            off = PACK in disabled()
            act.enable(PACK)
            on = PACK not in disabled()
            results["Q1 kit disable/enable round-trip"] = off and on
        except Exception as e:                       # noqa: BLE001 -- a spike reports, it does not hide
            results["Q1 kit disable/enable round-trip"] = f"raised {type(e).__name__}: {e}"

        engine.tree_extensions.append(graft_patches)
        tree = build_engine_tree(engine)
        keys = [f"ckupdater:{PACK}:{p}" for p, _, _ in PATCHES]
        results["Q2 patch nodes on the shared tree"] = all(k in tree for k in keys)
        results["Q2 card field (title) carried"] = (tree.nodes[keys[0]].get("title") == PATCHES[0][1]
                                                    if keys[0] in tree else False)

        try:
            act.disable("r1-converging")
            results["Q3 patch disable via activation verb"] = "r1-converging" in disabled()
        except Exception as e:                       # noqa: BLE001
            results["Q3 patch disable via activation verb"] = f"refused ({type(e).__name__}: {e})"
        results["control: non-kit name written to disabled_kits"] = "r1-converging" in disabled()

        act.enable("r1-converging")                  # undo the control's write before the CLI check
        buf, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
            try:
                rc = engine.run(["kit", "disable", "r1-converging"])
            except SystemExit as e:
                rc = e.code
        results["Q3b CLI `kit disable <patch>` rc"] = rc
        results["Q3b CLI wrote the patch into disabled_kits"] = "r1-converging" in disabled()
        results["Q3b CLI said"] = (buf.getvalue() + err.getvalue()).strip().splitlines()[-1:] or "-"

        store = engine.property_store
        try:
            store.set(f"{keys[0]}.activation", "inactive")
            got = engine.property_store.get(f"{keys[0]}.activation")
            results["Q4 property store round-trip"] = got == "inactive"
            results["Q4 stored under cfg/"] = sorted(p.name for p in cfg.iterdir())
        except Exception as e:                       # noqa: BLE001
            results["Q4 property store round-trip"] = f"raised {type(e).__name__}: {e}"
    results["isolation: ~/.ckupdater untouched"] = home_cfg.exists() == home_before
    for k, v in results.items():
        print(f"{k:52} {v}")


if __name__ == "__main__":
    main()
