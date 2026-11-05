"""Show the spinner's colours on this terminal: a few stages and a climbing counter, about six seconds.
Usage: python tests/one-offs/spinner_demo.py   (from the repository root, so the checkout's code is used)"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ck3_save_migrator.spinner import Spinner  # noqa: E402

with Spinner(True) as sp:
    sp.update("reading the whole save (98 MB)")
    time.sleep(1.5)
    for i in range(1, 27):
        sp.update(f"checking R{i} empty-modifiers ({i} of 26)")
        time.sleep(0.18)
print("done")
