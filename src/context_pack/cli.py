"""Command-line interface for context-pack."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .core import (
    DEFAULT_MAX_BYTES,
    DEFAULT_MAX_TOKENS,
    ContextPackError,
    build_context_pack,
    render_json,
    render_markdown,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="context-pack",
        description="Build a deterministic, bounded context pack from a Git repository.",
    )
    parser.add_argument(
        "files",
        nargs="*",
        metavar="FILE",
        help="explicit files or directories; omit them to use changed files",
    )
    parser.add_argument(
        "-C",
        "--repository",
        default=".",
        metavar="DIR",
        help="repository to inspect (default: current directory)",
    )
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument(
        "--changed",
        action="store_true",
        help="use Git changes relative to HEAD (the default when no files are given)",
    )
    parser.add_argument(
        "--base",
        metavar="REV",
        help="compare changes against REV instead of HEAD; implies --changed",
    )
    parser.add_argument(
        "--max-bytes",
        type=_nonnegative_int,
        default=DEFAULT_MAX_BYTES,
        metavar="N",
        help=f"maximum source bytes to include (default: {DEFAULT_MAX_BYTES})",
    )
    parser.add_argument(
        "--max-tokens",
        type=_nonnegative_int,
        default=DEFAULT_MAX_TOKENS,
        metavar="N",
        help=f"maximum estimated tokens to include (default: {DEFAULT_MAX_TOKENS})",
    )
    parser.add_argument(
        "--include-ignored",
        action="store_true",
        help="allow explicitly selected or changed files matched by Git ignore rules",
    )
    parser.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="output format (default: markdown)",
    )
    parser.add_argument(
        "-o",
        "--output",
        metavar="PATH",
        help="write the pack to PATH instead of standard output",
    )
    return parser


def _nonnegative_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be zero or greater")
    return parsed


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.base and args.files:
        parser.error("--base cannot be combined with explicit FILE arguments")
    try:
        pack = build_context_pack(
            args.repository,
            files=args.files,
            changed=args.changed or bool(args.base),
            base=args.base,
            max_bytes=args.max_bytes,
            max_tokens=args.max_tokens,
            include_ignored=args.include_ignored,
        )
        rendered = render_json(pack) if args.format == "json" else render_markdown(pack)
        if args.output:
            output = Path(args.output)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(rendered, encoding="utf-8")
        else:
            sys.stdout.write(rendered)
    except ContextPackError as exc:
        print(f"context-pack: error: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"context-pack: error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
