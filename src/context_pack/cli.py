"""Build deterministic source context and verify its provenance manifest."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from . import __version__

EXCLUDED_DIRS = frozenset({
    ".git", ".venv", "venv", "node_modules", "__pycache__",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", "build", "dist",
})
MANIFEST_SCHEMA = "context-pack/manifest/v1"
VERIFY_SCHEMA = "context-pack/verify/v1"
DIFF_SCHEMA = "context-pack/diff/v1"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _relative_path(root: Path, path: Path) -> str | None:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return None


def _absolute_path(path: Path) -> Path:
    """Make a path absolute without resolving a leaf symlink first."""
    return path.expanduser().absolute()


def _safe_artifact(path: Path, label: str) -> None:
    if path.is_symlink():
        raise ValueError(f"{label} must not be a symlink")
    if path.exists() and path.stat().st_nlink > 1:
        raise ValueError(f"{label} must not be a hard-link alias")


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _safe_artifact(path, "output")
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def _render_body(files: list[dict[str, Any]]) -> str:
    blocks = []
    quote = chr(96)
    for row in files:
        text = row["text"]
        longest = max((len(part) for part in text.split("\n") if part.startswith(quote)), default=0)
        fence = quote * max(3, longest + 1)
        blocks.append(f"## {row['path']}\n\n{fence}text\n{text}\n{fence}")
    return "\n\n".join(blocks)


def _collect(root: Path, budget: int, excluded: set[str], artifacts: set[Path]) -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    total = 0
    candidates: list[Path] = []

    def walk_error(error: OSError) -> None:
        raise error

    for directory, dirs, names in os.walk(root, followlinks=False, onerror=walk_error):
        base = Path(directory)
        dirs[:] = sorted(name for name in dirs if name not in excluded and not (base / name).is_symlink())
        candidates.extend(base / name for name in names)

    for path in sorted(candidates, key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix()
        resolved = path.resolve()
        if path.is_symlink():
            skipped.append({"path": relative, "reason": "symlink"})
            continue
        if resolved in artifacts:
            continue
        if not path.is_file():
            skipped.append({"path": relative, "reason": "not_regular_file"})
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
        files.append({"path": relative, "bytes": len(data), "sha256": _sha256(data), "text": text})
        total += len(data)

    body = _render_body(files)
    rendered = "# Context pack\n\n" + body + "\n"
    return {
        "files": files,
        "skipped": skipped,
        "bytes": total,
        "body": body,
        "body_sha256": _sha256(body.encode("utf-8")),
        "pack": rendered,
        "pack_sha256": _sha256(rendered.encode("utf-8")),
    }


def _manifest(
    root: Path,
    output: Path | None,
    manifest_path: Path | None,
    budget: int,
    excluded: set[str],
    selection: dict[str, Any],
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema": MANIFEST_SCHEMA,
        "tool": {"name": "context-pack", "version": __version__},
        "selection": {
            "max_bytes": budget,
            "excluded_dirs": sorted(excluded),
            "ordering": "relative-path-ascending",
            "encoding": "utf-8",
        },
        "artifacts": {
            "output": _relative_path(root, output) if output else None,
            "manifest": _relative_path(root, manifest_path) if manifest_path else None,
        },
        "bytes": selection["bytes"],
        "body_sha256": selection["body_sha256"],
        "pack_sha256": selection["pack_sha256"],
        "files": [
            {"path": row["path"], "bytes": row["bytes"], "sha256": row["sha256"]}
            for row in selection["files"]
        ],
        "skipped": selection["skipped"],
    }
    result["manifest_sha256"] = _sha256(_canonical_json(result))
    return result


def _manifest_without_digest(manifest: dict[str, Any]) -> dict[str, Any]:
    unsigned = dict(manifest)
    unsigned.pop("manifest_sha256", None)
    return unsigned


def _load_manifest(path: Path, label: str) -> tuple[Path, dict[str, Any]]:
    """Load and authenticate a manifest before using any of its selection data."""
    path = _absolute_path(path)
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"{label} manifest must be an existing regular file")
    if path.stat().st_nlink > 1:
        raise ValueError(f"{label} manifest must not be a hard-link alias")
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid {label} manifest: {error}") from error
    if not isinstance(manifest, dict) or manifest.get("schema") != MANIFEST_SCHEMA:
        raise ValueError(f"{label} manifest schema must be {MANIFEST_SCHEMA}")
    expected_digest = manifest.get("manifest_sha256")
    actual_digest = _sha256(_canonical_json(_manifest_without_digest(manifest)))
    if expected_digest != actual_digest:
        raise ValueError(f"{label} manifest_sha256_mismatch")
    files = manifest.get("files")
    if not isinstance(files, list):
        raise ValueError(f"{label} manifest files are invalid")
    for row in files:
        if not isinstance(row, dict) or not isinstance(row.get("path"), str):
            raise ValueError(f"{label} manifest files are invalid")
        if not isinstance(row.get("bytes"), int) or row["bytes"] < 0:
            raise ValueError(f"{label} manifest files are invalid")
        digest = row.get("sha256")
        if not isinstance(digest, str) or len(digest) != 64:
            raise ValueError(f"{label} manifest files are invalid")
    return path, manifest


def _change(before: Any, after: Any, field: str) -> dict[str, Any]:
    return {"field": field, "before": before, "after": after}


def diff_manifests(left_path: Path, right_path: Path, check: bool = False) -> dict[str, Any]:
    """Compare two authenticated manifests without reading source file contents."""
    left_path, left = _load_manifest(left_path, "left")
    right_path, right = _load_manifest(right_path, "right")

    left_files = {row["path"]: row for row in left["files"]}
    right_files = {row["path"]: row for row in right["files"]}
    added = [right_files[path] for path in sorted(right_files.keys() - left_files.keys())]
    removed = [left_files[path] for path in sorted(left_files.keys() - right_files.keys())]
    changed = [
        {"path": path, "before": left_files[path], "after": right_files[path]}
        for path in sorted(left_files.keys() & right_files.keys())
        if left_files[path] != right_files[path]
    ]

    left_skipped = {json.dumps(row, ensure_ascii=False, sort_keys=True): row for row in left.get("skipped", [])}
    right_skipped = {json.dumps(row, ensure_ascii=False, sort_keys=True): row for row in right.get("skipped", [])}
    skipped_added = [right_skipped[key] for key in sorted(right_skipped.keys() - left_skipped.keys())]
    skipped_removed = [left_skipped[key] for key in sorted(left_skipped.keys() - right_skipped.keys())]

    config_changes = []
    for field in ("max_bytes", "excluded_dirs", "ordering", "encoding"):
        before = left.get("selection", {}).get(field)
        after = right.get("selection", {}).get(field)
        if before != after:
            config_changes.append(_change(before, after, f"selection.{field}"))
    tool_changes = []
    for field in ("name", "version"):
        before = left.get("tool", {}).get(field)
        after = right.get("tool", {}).get(field)
        if before != after:
            tool_changes.append(_change(before, after, f"tool.{field}"))
    artifact_changes = []
    for field in ("output", "manifest"):
        before = left.get("artifacts", {}).get(field)
        after = right.get("artifacts", {}).get(field)
        if before != after:
            artifact_changes.append(_change(before, after, f"artifacts.{field}"))

    digest_changes = {}
    for field in ("bytes", "body_sha256", "pack_sha256"):
        before = left.get(field)
        after = right.get(field)
        if before != after:
            digest_changes[field] = {"before": before, "after": after}

    content_same = not any((added, removed, changed, skipped_added, skipped_removed, config_changes, tool_changes, digest_changes))
    result = {
        "schema": DIFF_SCHEMA,
        "ok": True,
        "same": content_same,
        "check": check,
        "left_manifest_sha256": left.get("manifest_sha256"),
        "right_manifest_sha256": right.get("manifest_sha256"),
        "changes": {
            "files": {"added": added, "removed": removed, "changed": changed},
            "skipped": {"added": skipped_added, "removed": skipped_removed},
            "selection": config_changes,
            "tool": tool_changes,
            # Output locations are intentionally reported but do not make two
            # otherwise identical source packs different across machines.
            "artifacts": artifact_changes,
            "digests": digest_changes,
        },
        "manifests": {"left": str(left_path), "right": str(right_path)},
    }
    result["summary"] = {
        "added": len(added),
        "removed": len(removed),
        "changed": len(changed),
        "skipped_added": len(skipped_added),
        "skipped_removed": len(skipped_removed),
        "config_changes": len(config_changes),
        "tool_changes": len(tool_changes),
        "artifact_changes": len(artifact_changes),
        "digest_changes": len(digest_changes),
    }
    return result


def build(
    root: Path,
    output: Path,
    budget: int,
    excluded: set[str],
    manifest_path: Path | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    output = _absolute_path(output)
    if budget < 0:
        raise ValueError("--max-bytes must be non-negative")
    if not root.is_dir():
        raise ValueError("root must be an existing directory")
    _safe_artifact(output, "output")
    output_resolved = output.resolve()
    if manifest_path is not None:
        manifest_path = _absolute_path(manifest_path)
        _safe_artifact(manifest_path, "manifest")
        manifest_resolved = manifest_path.resolve()
        if manifest_path == output:
            raise ValueError("manifest and output must be different paths")
        if manifest_resolved == output_resolved:
            raise ValueError("manifest and output must be different paths")
    else:
        manifest_resolved = None

    artifacts = {output_resolved}
    if manifest_resolved is not None:
        artifacts.add(manifest_resolved)
    selection = _collect(root, budget, excluded, artifacts)
    _atomic_write(output, selection["pack"])
    result: dict[str, Any] = {
        "schema": "context-pack/v1",
        "root": str(root),
        "files": [row["path"] for row in selection["files"]],
        "bytes": selection["bytes"],
        "sha256": selection["body_sha256"],
        "excluded_dirs": sorted(excluded),
        "skipped": selection["skipped"],
    }
    if manifest_path is not None:
        manifest = _manifest(root, output_resolved, manifest_resolved, budget, excluded, selection)
        _atomic_write(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        result["manifest"] = str(manifest_path)
        result["manifest_sha256"] = manifest["manifest_sha256"]
    return result


def verify(root: Path, manifest_path: Path, output_override: Path | None = None) -> dict[str, Any]:
    root = root.expanduser().resolve()
    if not root.is_dir():
        raise ValueError("root must be an existing directory")
    manifest_path, manifest = _load_manifest(manifest_path, "target")

    errors: list[str] = []
    expected_digest = manifest.get("manifest_sha256")

    selection_config = manifest.get("selection")
    if not isinstance(selection_config, dict):
        raise ValueError("manifest selection is invalid")
    budget = selection_config.get("max_bytes")
    excluded_raw = selection_config.get("excluded_dirs")
    if (
        not isinstance(budget, int)
        or isinstance(budget, bool)
        or budget < 0
        or not isinstance(excluded_raw, list)
        or any(not isinstance(name, str) for name in excluded_raw)
    ):
        raise ValueError("manifest selection is invalid")
    excluded = set(excluded_raw)

    artifacts_config = manifest.get("artifacts")
    if not isinstance(artifacts_config, dict):
        raise ValueError("manifest artifacts are invalid")
    recorded_output = artifacts_config.get("output")
    recorded_manifest = artifacts_config.get("manifest")
    artifacts: set[Path] = {manifest_path}
    if isinstance(recorded_output, str):
        output_candidate = _absolute_path(root / recorded_output)
        artifacts.add(output_candidate.resolve())
    if isinstance(recorded_manifest, str):
        manifest_candidate = _absolute_path(root / recorded_manifest)
        artifacts.add(manifest_candidate.resolve())
    if output_override is not None:
        output_override = _absolute_path(output_override)
        _safe_artifact(output_override, "output")
        artifacts.add(output_override.resolve())

    selection = _collect(root, budget, excluded, artifacts)
    current = _manifest(
        root,
        (root / recorded_output).resolve() if isinstance(recorded_output, str) else None,
        (root / recorded_manifest).resolve() if isinstance(recorded_manifest, str) else None,
        budget,
        excluded,
        selection,
    )
    if _manifest_without_digest(manifest) != _manifest_without_digest(current):
        errors.append("source_selection_mismatch")

    pack_state = "unknown"
    output_path = output_override
    if output_path is None and isinstance(recorded_output, str):
        output_path = _absolute_path(root / recorded_output)
    if output_path is not None:
        output_path = _absolute_path(output_path)
        if output_path.is_symlink() or (output_path.exists() and output_path.stat().st_nlink > 1):
            errors.append("pack_alias")
            pack_state = "mismatch"
        elif not output_path.is_file():
            errors.append("pack_missing")
            pack_state = "mismatch"
        else:
            pack_digest = _sha256(output_path.read_bytes())
            if pack_digest != manifest.get("pack_sha256"):
                errors.append("pack_sha256_mismatch")
                pack_state = "mismatch"
            else:
                pack_state = "matched"

    return {
        "schema": VERIFY_SCHEMA,
        "ok": not errors,
        "manifest_sha256": expected_digest,
        "current_manifest_sha256": current["manifest_sha256"],
        "pack_state": pack_state,
        "errors": errors,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="context-pack")
    parser.add_argument("--version", action="version", version=f"context-pack {__version__}")
    parser.add_argument("command", choices=["build", "verify", "diff"])
    parser.add_argument("root", nargs="?", default=".")
    parser.add_argument("other", nargs="?")
    parser.add_argument("--max-bytes", type=int, default=12000)
    parser.add_argument("--out", default="context-pack.md")
    parser.add_argument("--manifest", default=None)
    parser.add_argument("--check", action="store_true", help="for diff, exit 1 when manifests differ")
    parser.add_argument("--exclude-dir", action="append", default=[], metavar="NAME")
    return parser


def main(argv=None):
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        root = Path(args.root).expanduser().resolve()
        if args.command == "verify":
            if not args.manifest:
                raise ValueError("verify requires --manifest PATH")
            result = verify(root, Path(args.manifest), Path(args.out) if args.out != "context-pack.md" else None)
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0 if result["ok"] else 1

        if args.command == "diff":
            if not args.other:
                raise ValueError("diff requires LEFT_MANIFEST RIGHT_MANIFEST")
            result = diff_manifests(Path(args.root), Path(args.other), args.check)
            print(json.dumps(result, indent=2, sort_keys=True))
            return 1 if args.check and not result["same"] else 0

        output = Path(args.out).expanduser()
        manifest_path = Path(args.manifest).expanduser() if args.manifest else None
        result = build(root, output, args.max_bytes, EXCLUDED_DIRS | set(args.exclude_dir), manifest_path)
    except (OSError, ValueError) as error:
        print(json.dumps({"schema": "context-pack/error/v1", "ok": False, "error": str(error)}, sort_keys=True))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
