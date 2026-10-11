"""Entry point that allows `python -m gsearch`."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())