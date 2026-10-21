"""Command-line interface: `subforest build <path|sitemap.xml> --db corpus.db`."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from subforest.build import build_corpus
from subforest.store import TreeStore


def _build(args: argparse.Namespace) -> int:
    source: Path = args.source
    db: Path = args.db
    if not source.exists():
        print(f"error: {source} does not exist", file=sys.stderr)
        return 2
    if db.exists():
        if not args.force:
            print(f"error: {db} already exists (use --force to replace it)", file=sys.stderr)
            return 2
        db.unlink()
    result = build_corpus(source, corpus_id=args.corpus_id, max_chunk_chars=args.max_chunk_chars)
    with TreeStore(db) as store:
        result.write(store)
    docs = sum(n.kind == "doc" for n in result.nodes)
    print(f"built {db}: {len(result.nodes)} nodes, {docs} docs, {len(result.chunks)} chunks")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return its exit code.

    Example:
        >>> main(["build", "missing-dir", "--db", "x.db"])
        2
    """
    parser = argparse.ArgumentParser(prog="subforest")
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build", help="build a tree database from Markdown files or a sitemap.xml")
    build.add_argument("source", type=Path, help="directory of Markdown files, or a local sitemap.xml")
    build.add_argument("--db", type=Path, required=True, help="SQLite file to create")
    build.add_argument("--corpus-id", help="corpus id (default: directory name)")
    build.add_argument("--max-chunk-chars", type=int, default=1000)
    build.add_argument("--force", action="store_true", help="replace --db if it exists")
    build.set_defaults(func=_build)
    args = parser.parse_args(argv)
    code: int = args.func(args)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
