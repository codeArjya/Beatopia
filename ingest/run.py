"""Ingest entrypoint (WS1). Usage per docs/handoff/WS1-data-stems.md §6:

uv run --project ingest python -m ingest.run --source freesound --limit 20
uv run --project ingest python -m ingest.run --hero 80
"""

import argparse


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", choices=["freesound", "jamendo", "fma"])
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--hero", type=int, help="pre-separate stems for the N best tracks")
    parser.parse_args(argv)
    raise NotImplementedError("WS1: ingest pipeline")


if __name__ == "__main__":
    main()
