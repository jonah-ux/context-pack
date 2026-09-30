"""Core library for building deterministic repository context packs."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


DEFAULT_MAX_BYTES = 200_000
DEFAULT_MAX_TOKENS = 50_000


class ContextPackError(RuntimeError):
    """Raised when a repository cannot be inspected safely."""


@dataclass(frozen=True)
class Exclusion:
    """A candidate path that was not included and the reason why."""

    path: str
    reason: str
    detail: str = ""

    def to_dict(self) -> dict[str, str]:
        value = {"path": self.path, "reason": self.reason}
        if self.detail:
            value["detail"] = self.detail
        return value


@dataclass(frozen=True)
class IncludedFile:
    """A text file included in a context pack."""

    path: str
    content: str
    byte_count: int
    token_count: int
    sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "bytes": self.byte_count,
            "tokens": self.token_count,
            "sha256": self.sha256,
            "content": self.content,
        }


@dataclass(frozen=True)
class ContextPack:
    """The result of a deterministic context-pack build."""

    repository: str
    selection: str
    base: str | None
    max_bytes: int
    max_tokens: int
    files: tuple[IncludedFile, ...]
    exclusions: tuple[Exclusion, ...]

    @property
    def total_bytes(self) -> int:
        return sum(item.byte_count for item in self.files)

    @property
    def total_tokens(self) -> int:
        return sum(item.token_count for item in self.files)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation with stable field values."""

        return {
            "version": 1,
            "repository": self.repository,
            "selection": self.selection,
            "base": self.base,
            "budgets": {
                "max_bytes": self.max_bytes,
                "max_tokens": self.max_tokens,
            },
            "totals": {
                "files": len(self.files),
                "bytes": self.total_bytes,
                "tokens": self.total_tokens,
            },
            "files": [item.to_dict() for item in self.files],
            "exclusions": [item.to_dict() for item in self.exclusions],
        }


@dataclass(frozen=True)
class _Candidate:
    path: str
    raw: bytes
    content: str
    byte_count: int
    token_count: int
    sha256: str


def estimate_tokens(value: str | bytes) -> int:
    """Estimate tokens deterministically as four UTF-8 bytes per token.

    This is deliberately a transparent upper-bound-ish heuristic rather than a
    provider-specific tokenizer.  It is stable without a runtime dependency and
    is intended for budgeting, not billing or model accounting.
    """

    byte_count = len(value) if isinstance(value, bytes) else len(value.encode("utf-8"))
    return (byte_count + 3) // 4


def _git(root: Path, args: Sequence[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=root,
            text=True,
            encoding="utf-8",
            errors="surrogateescape",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except OSError as exc:
        raise ContextPackError("Git is required to inspect a repository") from exc
    if check and result.returncode != 0:
        detail = result.stderr.strip() or "git command failed"
        raise ContextPackError(detail)
    return result


def find_repository_root(repository: str | os.PathLike[str] = ".") -> Path:
    """Resolve *repository* to its Git worktree root."""

    requested = Path(repository).expanduser()
    if not requested.exists():
        raise ContextPackError(f"repository does not exist: {repository}")
    requested = requested.resolve()
    if not requested.is_dir():
        raise ContextPackError(f"repository is not a directory: {repository}")
    result = _git(requested, ["rev-parse", "--show-toplevel"])
    root = Path(result.stdout.strip()).resolve()
    if not root.is_dir():
        raise ContextPackError(f"Git reported a missing worktree root: {root}")
    return root


def _split_nul(value: str) -> list[str]:
    return [item for item in value.split("\0") if item]


def _has_head(root: Path) -> bool:
    return _git(root, ["rev-parse", "--verify", "HEAD"], check=False).returncode == 0


def _changed_paths(root: Path, base: str | None, include_ignored: bool = False) -> list[str]:
    """Return modified tracked and non-ignored untracked paths."""

    diff_args = ["diff", "--name-only", "-z", "--diff-filter=ACDMRTUXB"]
    if base:
        diff_args.append(base)
    elif _has_head(root):
        diff_args.append("HEAD")
    diff_args.extend(["--"])
    tracked = _split_nul(_git(root, diff_args).stdout)
    if not base and not _has_head(root):
        staged = _split_nul(
            _git(root, ["diff", "--cached", "--name-only", "-z", "--diff-filter=ACDMRTUXB", "--"]).stdout
        )
        tracked = sorted(set(tracked + staged))
    untracked = _split_nul(
        _git(root, ["ls-files", "--others", "--exclude-standard", "-z"]).stdout
    )
    if include_ignored:
        ignored = _split_nul(
            _git(root, ["ls-files", "--others", "--ignored", "--exclude-standard", "-z"]).stdout
        )
        untracked = sorted(set(untracked + ignored))
    return sorted(set(tracked + untracked))


def _relative_path(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _is_within(root: Path, path: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _explicit_paths(root: Path, requested: Iterable[str]) -> tuple[list[str], list[Exclusion]]:
    candidates: list[str] = []
    exclusions: list[Exclusion] = []
    seen: set[str] = set()

    for raw_value in requested:
        raw = str(raw_value)
        supplied = Path(raw).expanduser()
        target = supplied if supplied.is_absolute() else root / supplied
        # Resolve for containment, but do not require the path to exist first.
        resolved = target.resolve(strict=False)
        display = raw.replace(os.sep, "/")
        if not _is_within(root, resolved):
            exclusions.append(
                Exclusion(display, "outside-repository", "explicit paths must stay inside the Git worktree")
            )
            continue
        if not resolved.exists():
            exclusions.append(Exclusion(_relative_path(root, resolved), "missing", "path does not exist"))
            continue
        if resolved.is_dir():
            for current, directories, filenames in os.walk(resolved, followlinks=False):
                current_path = Path(current)
                directories[:] = sorted(name for name in directories if name != ".git")
                for name in sorted(filenames):
                    child = current_path / name
                    if not child.is_file():
                        continue
                    resolved_child = child.resolve()
                    if not _is_within(root, resolved_child):
                        continue
                    relative = _relative_path(root, resolved_child)
                    if relative not in seen:
                        seen.add(relative)
                        candidates.append(relative)
            continue
        relative = _relative_path(root, resolved)
        if relative not in seen:
            seen.add(relative)
            candidates.append(relative)
    return sorted(candidates), exclusions


def _is_ignored(root: Path, relative: str) -> bool:
    result = _git(root, ["check-ignore", "--no-index", "-q", "--", relative], check=False)
    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False
    # A malformed ignore configuration should not be silently treated as an
    # allow-list.  Git's diagnostic is useful to a caller.
    detail = result.stderr.strip() or "git check-ignore failed"
    raise ContextPackError(detail)


def _read_candidate(root: Path, relative: str) -> tuple[_Candidate | None, Exclusion | None]:
    path = root / relative
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return None, Exclusion(relative, "missing", "file disappeared while it was being read")
    except OSError as exc:
        return None, Exclusion(relative, "unreadable", str(exc))
    if b"\0" in raw:
        return None, Exclusion(relative, "binary", "NUL byte detected")
    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None, Exclusion(relative, "binary", "content is not valid UTF-8")
    return (
        _Candidate(
            path=relative,
            raw=raw,
            content=content,
            byte_count=len(raw),
            token_count=estimate_tokens(raw),
            sha256=hashlib.sha256(raw).hexdigest(),
        ),
        None,
    )


def build_context_pack(
    repository: str | os.PathLike[str] = ".",
    *,
    files: Sequence[str] | None = None,
    changed: bool = False,
    base: str | None = None,
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    include_ignored: bool = False,
) -> ContextPack:
    """Build a bounded pack from changed files or explicitly selected files.

    Files are considered in normalized POSIX path order.  A file is included
    only in its entirety, so neither budget can produce partial source.  Git
    ignore rules, duplicate content, binary data, and budget decisions are all
    represented in ``exclusions``.
    """

    if max_bytes < 0 or max_tokens < 0:
        raise ContextPackError("budgets must be zero or greater")
    root = find_repository_root(repository)
    explicit = list(files or [])
    if changed and explicit:
        raise ContextPackError("choose --changed or explicit files, not both")
    if base and explicit:
        raise ContextPackError("--base can only be used with changed files")

    if changed or not explicit:
        selection = "changed"
        candidates = _changed_paths(root, base, include_ignored)
        initial_exclusions: list[Exclusion] = []
    else:
        selection = "explicit"
        candidates, initial_exclusions = _explicit_paths(root, explicit)

    exclusions = list(initial_exclusions)
    eligible: list[_Candidate] = []
    seen_content: dict[str, str] = {}

    for relative in sorted(set(candidates)):
        path = root / relative
        if not path.exists():
            exclusions.append(Exclusion(relative, "missing", "file does not exist"))
            continue
        if not path.is_file():
            exclusions.append(Exclusion(relative, "not-file", "only regular files can be packed"))
            continue
        if not include_ignored and _is_ignored(root, relative):
            exclusions.append(Exclusion(relative, "ignored", "matched Git ignore rules"))
            continue
        candidate, exclusion = _read_candidate(root, relative)
        if exclusion is not None:
            exclusions.append(exclusion)
            continue
        assert candidate is not None
        previous = seen_content.get(candidate.sha256)
        if previous is not None:
            exclusions.append(
                Exclusion(relative, "duplicate", f"same content as {previous}")
            )
            continue
        seen_content[candidate.sha256] = relative
        eligible.append(candidate)

    included: list[IncludedFile] = []
    total_bytes = 0
    total_tokens = 0
    for candidate in eligible:
        if total_bytes + candidate.byte_count > max_bytes:
            exclusions.append(
                Exclusion(candidate.path, "byte-budget", f"would exceed {max_bytes} bytes")
            )
            continue
        if total_tokens + candidate.token_count > max_tokens:
            exclusions.append(
                Exclusion(candidate.path, "token-budget", f"would exceed {max_tokens} tokens")
            )
            continue
        included.append(
            IncludedFile(
                path=candidate.path,
                content=candidate.content,
                byte_count=candidate.byte_count,
                token_count=candidate.token_count,
                sha256=candidate.sha256,
            )
        )
        total_bytes += candidate.byte_count
        total_tokens += candidate.token_count

    exclusions.sort(key=lambda item: (item.path, item.reason, item.detail))
    return ContextPack(
        repository=root.name,
        selection=selection,
        base=base,
        max_bytes=max_bytes,
        max_tokens=max_tokens,
        files=tuple(included),
        exclusions=tuple(exclusions),
    )


# A short alias for library callers who prefer the noun used by the CLI.
build_pack = build_context_pack


def _language_for(path: str) -> str:
    suffix = Path(path).suffix.lower()
    return {
        ".py": "python",
        ".pyi": "python",
        ".js": "javascript",
        ".jsx": "jsx",
        ".ts": "typescript",
        ".tsx": "tsx",
        ".json": "json",
        ".md": "markdown",
        ".toml": "toml",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".sh": "bash",
        ".css": "css",
        ".html": "html",
        ".rs": "rust",
        ".go": "go",
        ".java": "java",
        ".sql": "sql",
    }.get(suffix, "text")


def render_json(pack: ContextPack) -> str:
    """Render *pack* as stable, human-readable JSON."""

    return json.dumps(pack.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _markdown_fence(content: str) -> str:
    longest = 0
    run = 0
    for char in content:
        if char == "`":
            run += 1
            longest = max(longest, run)
        else:
            run = 0
    return "`" * max(3, longest + 1)


def render_markdown(pack: ContextPack) -> str:
    """Render *pack* as deterministic Markdown, including exclusions."""

    lines = [
        "# Context pack",
        "",
        f"- Repository: `{pack.repository}`",
        f"- Selection: `{pack.selection}`",
        f"- Base: `{pack.base}`" if pack.base else "- Base: _(working tree)_",
        f"- Included: {len(pack.files)} file(s), {pack.total_bytes} bytes, {pack.total_tokens} estimated tokens",
        f"- Budget: {pack.max_bytes} bytes / {pack.max_tokens} estimated tokens",
        "",
        "## Included files",
        "",
    ]
    if not pack.files:
        lines.append("_(none)_")
        lines.append("")
    for item in pack.files:
        fence = _markdown_fence(item.content)
        lines.extend([f"### `{item.path}`", "", f"{fence}{_language_for(item.path)}"])
        lines.extend(item.content.splitlines())
        if item.content.endswith("\n"):
            # splitlines() omits the final separator, which is exactly what a
            # fenced block needs before its closing fence.
            pass
        lines.extend([fence, ""])

    lines.extend(["## Exclusions", ""])
    if not pack.exclusions:
        lines.append("_(none)_")
    else:
        for exclusion in pack.exclusions:
            detail = f" — {exclusion.detail}" if exclusion.detail else ""
            lines.append(f"- `{exclusion.path}` — **{exclusion.reason}**{detail}")
    return "\n".join(lines).rstrip() + "\n"


__all__ = [
    "ContextPack",
    "ContextPackError",
    "Exclusion",
    "IncludedFile",
    "DEFAULT_MAX_BYTES",
    "DEFAULT_MAX_TOKENS",
    "build_context_pack",
    "build_pack",
    "estimate_tokens",
    "find_repository_root",
    "render_json",
    "render_markdown",
]
