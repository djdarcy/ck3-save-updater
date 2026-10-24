"""Allow running as: python -m ck3_save_migrator"""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
