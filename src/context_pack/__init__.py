"""Deterministic, Git-aware context packs for Python and the command line."""

from .core import (
    ContextPack,
    ContextPackError,
    Exclusion,
    IncludedFile,
    build_context_pack,
    build_pack,
    estimate_tokens,
    render_json,
    render_markdown,
)

__all__ = [
    "ContextPack",
    "ContextPackError",
    "Exclusion",
    "IncludedFile",
    "build_context_pack",
    "build_pack",
    "estimate_tokens",
    "render_json",
    "render_markdown",
]

__version__ = "0.1.0"
