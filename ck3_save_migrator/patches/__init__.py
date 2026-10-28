"""Patches: the migrator's rules written as files.

A pack is a folder of patch folders with a ``pack.toml``; a patch is a folder with a ``patch.toml`` (see
``docs/writing-a-patch.md``). ``rules_from_pack`` turns a pack into ``Rule`` objects; the shipped pack
``to_1_20`` holds the 19 registered rules.
"""

from __future__ import annotations

from .engine import Plan, apply_patch, plan
from .model import FORMAT, OPS, EditSpec, Pack, Patch, PatchError, load_pack, load_patch
from .pack import SHIPPED, read_pack, rules_from_pack, shipped_pack_folder, status, verdict

__all__ = ["FORMAT", "OPS", "EditSpec", "Pack", "Patch", "PatchError", "Plan", "SHIPPED", "apply_patch",
           "load_pack", "load_patch", "plan", "read_pack", "rules_from_pack", "shipped_pack_folder", "status",
           "verdict"]
