#!/usr/bin/env bash
set -euo pipefail

# Run this after installing context-pack (for example: python -m pip install .).
context_pack_bin="${CONTEXT_PACK_BIN:-context-pack}"
demo_dir="$(mktemp -d "${TMPDIR:-/tmp}/context-pack-demo.XXXXXX")"
trap 'rm -rf "$demo_dir"' EXIT

cd "$demo_dir"
git init -q
git config user.name "context-pack demo"
git config user.email "demo@example.invalid"
printf 'def greet(name):\n    return f"hello {name}"\n' > app.py
printf 'generated output\n' > generated.txt
printf 'generated.txt\n' > .gitignore
git add .
git commit -qm "initial demo repository"
printf 'def greet(name):\n    return f"hello, {name}!"\n' > app.py
printf 'new file\n' > notes.md

printf '%s\n' 'context-pack demo (changed files, Markdown):'
"$context_pack_bin" --changed --format markdown
