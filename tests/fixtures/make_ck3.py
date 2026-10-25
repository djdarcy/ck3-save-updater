"""Build small synthetic CK3 ``.ck3`` saves for tests and one-off probes.

No real save ships with the repo; these few-KB files reproduce the layout of a
kind-02 (UnifiedText) save: the ``SAV...`` header, a plaintext ``meta_data``
block, and a zip whose ``gamestate`` member begins with the same block.

Importable from tests (``from tests.fixtures.make_ck3 import build_ck3``) and from
one-offs (add the project root to ``sys.path`` first).
"""

from __future__ import annotations

import io
import zipfile

DEFAULT_META = (
    b"meta_data={\n"
    b"\tsave_game_version=8\n"
    b"\tversion=\"1.8.1\"\n"
    b"\tportraits_version=3\n"
    b"\tmeta_date=987.10.27\n"
    # an unbalanced brace and escaped quotes inside a string: a brace counter that
    # does not skip strings ends the block early
    b"\tmeta_player_name=\"Arch-Abbot Test } \\\"quoted\\\"\"\n"
    b"\tmods={ \"mod/wos.mod\" \"mod/ugc_2507209632.mod\" }\n"
    b"\tgame_rules={\n"
    b"\t\tsettings={ \"\" \"\" normal_difficulty }\n"
    b"\t}\n"
    b"\tironman=no\n"
    b"}\n"
)

DEFAULT_BODY = (
    b"random_seed=4942029\n"
    b"date=987.10.27\n"
    b"living={\n"
    b"1={\n"
    b"\tfirst_name=\"Beidh\"\n"
    b"\tbirth=950.3.9\n"
    b"\tfaith=12\n"
    b"\tskill={ 6 4 8 7 7 5 }\n"
    b"}\n"
    b"2={\n"
    b"\tfirst_name=\"Simin\"\n"
    b"\tbirth=951.3.9\n"
    b"\tfemale=yes\n"
    b"}\n"
    b"}\n"
    b"landed_titles={\n"
    b"\tlanded_titles={\n"
    b"0={\n"
    b"\tkey=\"e_ireland\"\n"
    b"\tname=\"Ireland\"\n"
    b"\tdate=930.4.12\n"
    b"}\n"
    b"}\n"
    b"}\n"
)


# A gamestate body with the layouts the scanner must survive, each taken from the
# real 1.8.1 / 1.20 saves: a quoted brace, escaped quotes, rgb { } values, two keys on
# one tab-separated line, an empty-key cooldown, the game's anonymous "}\n {" list
# layout, a decoy faiths={ 0 1 } id list inside religions next to the real faiths
# database, inner landed_titles, and a repeated top-level key.
NESTED_BODY = (
    b"random_seed=4942029\n"
    b"living={\n"
    b"1={\n"
    b"\tfirst_name=\"Beidh {not a block\"\n"
    b"\tfaith=12\n"
    b"\tskill={ 6 4 8 7 7 5 }\n"
    b"\tweight={\n"
    b"\t\tbase=-18\n"
    b"\t\tcurrent=12\n"
    b"\t}\n"
    b"\tlanded_data={\n"
    b"\t\tdecision_cooldowns={\n"
    b"\t\t\t=-5000.1.1\n"
    b"\t\t}\n"
    b"\t}\n"
    b"}\n"
    b"\n"
    b"2={\n"
    b"\tfirst_name=\"Simin \\\"the } quoted\\\"\"\n"
    b"\tfemale=yes\n"
    b"\tfaith=12\n"
    b"\tcolor=rgb { 1 2 3 }\n"
    b"\talive_data={\n"
    b"\t\t\tmodifier=world_modifier\t\t\texpiration_date=9999.1.1\n"
    b"\t}\n"
    b"}\n"
    b"\n"
    b"}\n"
    b"religion={\n"
    b"\treligions={\n"
    b"\t\t0={\n"
    b"\t\t\ttag=\"christianity_religion\"\n"
    b"\t\t\tfaiths={ 0 1 }\n"
    b"\t\t}\n"
    b"\t}\n"
    b"\tfaiths={\n"
    b"\t\t0={\n"
    b"\t\t\ttag=\"catholic\"\n"
    b"\t\t}\n"
    b"\t\t1={\n"
    b"\t\t\ttag=\"orthodox\"\n"
    b"\t\t}\n"
    b"\t}\n"
    b"}\n"
    b"opinions={\n"
    b"\tactive_opinions={ {\n"
    b"\t\t\towner=1\n"
    b"\t\t\ttarget=2\n"
    b"\t\t\ttemporary_opinion={\n"
    b"\t\t\t\tmodifier=\"impressed_opinion\"\n"
    b"\t\t\t\tconverging={\n"
    b"\t\t\t\t\tdays=4709\n"
    b"\t\t\t\t\topinion=20.6\n"
    b"\t\t\t\t}\n"
    b"\t\t\t\tvalue=5\n"
    b"\t\t\t}\n"
    b"\t\t}\n"
    b" {\n"
    b"\t\t\towner=2\n"
    b"\t\t\ttarget=1\n"
    b"\t\t}\n"
    b" }\n"
    b"}\n"
    b"landed_titles={\n"
    b"\tdynamic_templates={ {\n"
    b"\t\t\tkey=\"x_x_1\"\n"
    b"\t\t}\n"
    b" }\n"
    b"\tlanded_titles={\n"
    b"0={\n"
    b"\tkey=\"k_papal_state\"\n"
    b"\tname=\"Papacy\"\n"
    b"\tadj=\"Papal\"\n"
    b"\tarticle=\"the \"\n"
    b"\tdate=976.3.4\n"
    b"}\n"
    b"1={\n"
    b"\tkey=\"e_ireland\"\n"
    b"\tname=\"Ireland\"\n"
    b"\tdate=930.4.12\n"
    b"}\n"
    b"\t}\n"
    b"}\n"
    b"triggered_event={ id=1 }\n"
    b"triggered_event={ id=2 }\n"
)


# One instance of each shape the unit-3 rules edit, in the layouts the 1.8.1 save uses.
RULES_META = (
    b"meta_data={\n"
    b"\tsave_game_version=8\n"
    b"\tversion=\"1.8.1\"\n"
    b"\tportraits_version=3\n"
    b"\tmeta_date=987.10.27\n"
    b"\tgame_rules={\n"
    b"\t\tsettings={ \"\" \"\" \"\" normal_difficulty default_cfp_baldtrait }\n"
    b"\t}\n"
    b"\n"
    b"\tironman=no\n"
    b"}\n"
)

RULES_BODY = (
    b"random_seed=4942029\n"
    b"landed_titles={\n"
    b"\tlanded_titles={\n"
    b"0={\n"
    b"\tkey=\"k_papal_state\"\n"
    b"\tholder=66845\n"
    b"\tname=\"Papacy\"\n"
    b"\tadj=\"Papal\"\n"
    b"\tarticle=\"the \"\n"
    b"\tdate=976.3.4\n"
    b"\tcoat_of_arms_id=7\n"
    b"\tdefault_coa=yes\n"
    b"}\n"
    b"18={\n"
    b"\tkey=\"e_black_horde\"\n"
    b"\tname=\"Black Horde\"\n"
    b"\tadj=\"Mongol\"\n"
    b"\tpre=\"Mongolo\"\n"
    b"\tdate=9999.1.1\n"
    b"\tcoat_of_arms_id=13\n"
    b"}\n"
    b"40={\n"
    b"\tkey=\"x_x_1848\"\n"
    b"\tname=\"Dynamic\"\n"
    b"\tdate=900.1.1\n"
    b"}\n"
    b"41={\n"
    b"\tkey=\"d_knights_hospitaler\"\n"
    b"\tholder=500\n"
    b"\tde_jure_liege=0\n"
    b"\tcoat_of_arms_id=20\n"
    b"}\n"
    b"\t}\n"
    b"}\n"
    b"living={\n"
    b"500={\n"
    b"\tfirst_name=\"Knut\"\n"
    b"\tdesc=\"a line\n=not a key\"\n"
    b"\tlanded_data={\n"
    b"\t\tdecision_cooldowns={\n"
    b"\t\t\t=-5000.1.1\n"
    b"\t\t\tconvert_to_witchcraft_decision=986.1.1\n"
    b"\t\t}\n"
    b"\t\tinteraction_cooldowns={\n"
    b"\t\t\t=-5000.1.1\n"
    b"\t\t}\n"
    b"\t\tliege_title=18\n"
    b"\t}\n"
    b"}\n"
    b"}\n"
    b"opinions={\n"
    b"\tactive_opinions={ {\n"
    b"\t\t\towner=1\n"
    b"\t\t\ttarget=2\n"
    b"\t\t\ttemporary_opinion={\n"
    b"\t\t\t\tmodifier=\"impressed_opinion\"\n"
    b"\t\t\t\tstart_date=974.12.2\n"
    b"\t\t\t\tconverging={\n"
    b"\t\t\t\t\tdays=4709\n"
    b"\t\t\t\t\topinion=20.6\n"
    b"\t\t\t\t}\n"
    b"\t\t\t\tvalue=5\n"
    b"\t\t\t}\n"
    b"\t\t\ttemporary_opinion={\n"
    b"\t\t\t\tmodifier=\"feast_opinion\"\n"
    b"\t\t\t\tconverging={\n"
    b"\t\t\t\t\ttotal_days=3650\n"
    b"\t\t\t\t\tdays=1411\n"
    b"\t\t\t\t\topinion=15\n"
    b"\t\t\t\t}\n"
    b"\t\t\t\tvalue=10\n"
    b"\t\t\t}\n"
    b"\t\t\tscripted_relations={\n"
    b"\t\t\t\tpotential_friend={\n"
    b"\t\t\t\t\tflags=\"AAAAAA==\"\n"
    b"\t\t\t\t}\n"
    b"\n"
    b"\t\t\t}\n"
    b"\t\t}\n"
    b" {\n"
    b"\t\t\towner=2\n"
    b"\t\t\ttarget=1\n"
    b"\t\t\tscripted_relations={\n"
    b"\t\t\t\tward={\n"
    b"\t\t\t\t\tflags=\"AQAAAA==\"\n"
    b"\t\t\t\t}\n"
    b"\t\t\t\tfriend={\n"
    b"\t\t\t\t\tflags=\"AAEAAA==\"\n"
    b"\t\t\t\t}\n"
    b"\t\t\t\trival={\n"
    b"\t\t\t\t\tflags=\"Aw==\"\n"
    b"\t\t\t\t}\n"
    b"\n"
    b"\t\t\t}\n"
    b"\t\t}\n"
    b" }\n"
    b"}\n"
    b"game_rules={\n"
    b"\tsetting={ \"\" \"\" \"\" normal_difficulty default_cfp_baldtrait }\n"
    b"}\n"
)

# The game-data side of the rules fixture: what a minimal <game>/common/landed_titles holds.
RULES_GAME_TITLES = (
    b"# comment with k_commented_out = { }\n"
    b"k_papal_state = { capital = c_roma }\n"
    b"d_knights_hospitaller = { }\n"
)
RULES_TITLE_CONVERSION = (
    b"# Renamed title keys\n"
    b"d_knights_hospitaler = d_knights_hospitaller\n"
)


def make_game_dir(root) -> "object":
    """Write a minimal game folder (common/landed_titles) under ``root``; return its path."""
    from pathlib import Path
    lt = Path(root) / "common" / "landed_titles"
    lt.mkdir(parents=True, exist_ok=True)
    (lt / "00_landed_titles.txt").write_bytes(RULES_GAME_TITLES)
    (lt / "title_conversion.lookup").write_bytes(RULES_TITLE_CONVERSION)
    return Path(root)


def build_ck3(meta: bytes = DEFAULT_META, body: bytes = DEFAULT_BODY, *, kind: int = 2,
              unknown: str = "01", random: str = "7d3b0037", newline: bytes = b"\n",
              meta_len: int | None = None, upper_hex: bool = False, plaintext_meta: bytes | None = None,
              member_name: str = "gamestate", extra_members: dict[str, bytes] | None = None,
              compresslevel: int = 1) -> bytes:
    """Return the bytes of a synthetic save.

    ``meta_len`` overrides the header length field (to fake a corrupt header);
    ``plaintext_meta`` overrides the plaintext copy (to fake disagreeing copies).
    ``compresslevel`` defaults to 1, unlike the writer's 6, so a re-deflate is
    always visible in the bytes.
    """
    gamestate = meta + body
    plain = meta if plaintext_meta is None else plaintext_meta
    length = len(plain) if meta_len is None else meta_len
    hdr = f"SAV{unknown}{kind:02x}{random}{length:08x}"
    if upper_hex:
        hdr = "SAV" + hdr[3:].upper()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=compresslevel) as z:
        zi = zipfile.ZipInfo(member_name, date_time=(1980, 1, 1, 0, 0, 0))
        zi.compress_type = zipfile.ZIP_DEFLATED
        # a ZipInfo ignores the archive-level compresslevel, so pass it per member
        z.writestr(zi, gamestate, compresslevel=compresslevel)
        for name, data in (extra_members or {}).items():
            zx = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            zx.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(zx, data, compresslevel=compresslevel)
    return hdr.encode("ascii") + newline + plain + buf.getvalue()
