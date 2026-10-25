"""Print the PLAIN_FIELDS literal for ck3_save_migrator/idschema.py: every integer field the field probe saw in the
reference's entries of a copyable kind that the schema does not already classify. Review the output by hand
before pasting: anything that looks like an id belongs in FIELDS instead.

Usage: python -I tests/one-offs/gen_plain_fields.py private/data/unit1/field_spaces.json
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ck3_save_migrator import idschema as S  # noqa: E402

COPYABLE = set(S.FIELDS) | {"coat_of_arms/coat_of_arms_manager_database", "characters"}


def main():
    data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    out = {}
    for kind, rows in data.items():
        k = "character" if kind == "characters" else kind
        if k not in COPYABLE:
            continue
        for r in rows:
            if r["ref_n"] and S.classify(k, r["path"]) is None:
                out.setdefault(k, []).append((r["path"], r["ref_max"]))
    print("PLAIN_FIELDS: dict[str, frozenset[str]] = {")
    for k in sorted(out):
        print(f'    "{k}": frozenset({{')
        for p, mx in sorted(out[k]):
            print(f'        "{p}",  # max {mx}')
        print("    }),")
    print("}")


if __name__ == "__main__":
    main()
