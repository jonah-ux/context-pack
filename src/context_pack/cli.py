"""Build deterministic source context without traversing dependency trees."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

from . import __version__


EXCLUDED_DIRS = frozenset({
    ".git", ".venv", "venv", "node_modules", "__pycache__",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", "build", "dist",
})


def build(root: Path, output: Path, budget: int, excluded: set[str]) -> dict:
    """Select UTF-8 regular files within a source-byte budget."""
    files = []
    skipped = []
    total = 0
    candidates = []

    def walk_error(error: OSError) -> None:
        raise error

    for directory, dirs, names in os.walk(root, followlinks=False, onerror=walk_error):
        base = Path(directory)
        dirs[:] = sorted(
            name for name in dirs
            if name not in excluded and not (base / name).is_symlink()
        )
        candidates.extend(base / name for name in names)
    for path in sorted(candidates, key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink() or path.resolve() == output:
            continue
        if not path.is_file():
            continue
        remaining = budget - total
        if path.stat().st_size > remaining:
            skipped.append({"path": relative, "reason": "byte_budget"})
            continue
        with path.open("rb") as handle:
            data = handle.read(remaining + 1)
        if len(data) > remaining:
            skipped.append({"path": relative, "reason": "byte_budget"})
            continue
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            skipped.append({"path": relative, "reason": "non_utf8"})
            continue
        files.append((relative, text))
        total += len(data)

    blocks = []
    for name, text in files:
        longest = max((len(part) for part in text.split("\n") if part.startswith("`")), default=0)
        fence = "`" * max(3, longest + 1)
        blocks.append(f"## {name}\n\n{fence}text\n{text}\n{fence}")
    body = "\n\n".join(blocks)
    output.write_text("# Context pack\n\n" + body + "\n", encoding="utf-8")
    return {
        "schema": "context-pack/v1",
        "root": str(root),
        "files": [name for name, _ in files],
        "bytes": total,
        "sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        "excluded_dirs": sorted(excluded),
        "skipped": skipped,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(prog="context-pack")
    parser.add_argument("--version", action="version", version=f"context-pack {__version__}")
    parser.add_argument("command", choices=["build"])
    parser.add_argument("root", nargs="?", default=".")
    parser.add_argument("--max-bytes", type=int, default=12000)
    parser.add_argument("--out", default="context-pack.md")
    parser.add_argument("--exclude-dir", action="append", default=[], metavar="NAME")
    args = parser.parse_args(argv)
    try:
        root = Path(args.root).expanduser().resolve()
        output_arg = Path(args.out).expanduser()
        if args.max_bytes < 0:
            raise ValueError("--max-bytes must be non-negative")
        if not root.is_dir():
            raise ValueError("root must be an existing directory")
        if output_arg.is_symlink():
            raise ValueError("output must not be a symlink")
        output = output_arg.resolve()
        result = build(root, output, args.max_bytes, EXCLUDED_DIRS | set(args.exclude_dir))
    except (OSError, ValueError) as error:
        print(json.dumps({"schema": "context-pack/error/v1", "ok": False, "error": str(error)}, sort_keys=True))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
