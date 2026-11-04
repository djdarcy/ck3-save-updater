"""Red-green for R25's tests: revert one behaviour at a time by patching the module in memory (the source file is
never edited), run tests/test_r25_successor_keys.py, and list which tests go red. Usage: python r25_redgreen.py"""
import sys

sys.path.insert(0, r"C:\code\ck3-save-migrator")
import pytest  # noqa: E402

from ck3_save_migrator.rules import to_1_20 as M  # noqa: E402

real_defined, real_in_field = M.defined_keys, M._in_field


class Collect:
    def __init__(self):
        self.red = []

    def pytest_runtest_logreport(self, report):
        if report.when == "call" and report.failed:
            self.red.append(report.nodeid.split("::")[-1])


def arm(name, setup):
    M.defined_keys, M._in_field = real_defined, real_in_field
    setup()
    c = Collect()
    pytest.main(["-q", "-p", "no:cacheprovider", r"C:\code\ck3-save-migrator\tests\test_r25_successor_keys.py"],
                plugins=[c])
    M.defined_keys, M._in_field = real_defined, real_in_field
    print(f"\n### {name}: {len(c.red)} red: {c.red}\n")


def no_field_check():
    M._in_field = lambda d, s, field: True


def no_still_defined_guard():          # the old key never counts as defined
    M.defined_keys = lambda roots, folder: real_defined(roots, folder) - {"teutonic_knights", "scholar_perk"}


def no_successor_guard():              # every successor counts as defined
    class Everything(set):
        def __contains__(self, k):
            return not k.endswith(("teutonic_knights", "scholar_perk")) and not k.endswith("_power_add_1_modifier") \
                and "scheme_power" not in k
    M.defined_keys = lambda roots, folder: Everything(real_defined(roots, folder))


def bom_not_stripped():
    import re
    from pathlib import Path

    def keys(roots, folder):
        out = set()
        for root in roots:
            base = Path(root) / "common" / folder
            if base.is_dir():
                for f in sorted(base.rglob("*.txt")):
                    out.update(m.group(1).decode() for m in re.finditer(rb"(?m)^([A-Za-z0-9_][\w.\-]*)\s*=\s*\{",
                                                                         f.read_bytes()))
        return out
    M.defined_keys = keys


if __name__ == "__main__":
    arm("control (nothing reverted)", lambda: None)
    arm("field check off", no_field_check)
    arm("still-defined guard off", no_still_defined_guard)
    arm("successor guard off", no_successor_guard)
    arm("BOM not stripped", bom_not_stripped)
