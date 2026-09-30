# Context Pack

![bounded context pack builder workflow](docs/header.svg)

**Build deterministic, budget-aware repository context for coding agents.**

[![CI](https://github.com/jonah-ux/context-pack/actions/workflows/ci.yml/badge.svg)](https://github.com/jonah-ux/context-pack/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%2B-3776ab)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-22c55e)](LICENSE)

Context Pack walks a repository in deterministic order, skips common generated directories,
stays under a byte budget, and writes a Markdown bundle with a SHA-256 digest. It is a small,
inspectable answer to “what context should this coding agent see?”

## Try it in 30 seconds

```bash
python -m pip install git+https://github.com/jonah-ux/context-pack.git@main
python demos/demo.py
```

Build a bounded pack from the current repository:

```bash
context-pack build . --max-bytes 12000 --out context-pack.md
```

The `context-pack/v1` JSON summary reports the selected files, byte count, root, and digest.
The Markdown output stays readable in a text editor and easy for an agent to ingest.

## Development

```bash
python -m unittest discover -s tests
python -m build --sdist --wheel
python demos/demo.py
```

The pack is bounded and deterministic; it is not a complete repository backup or a guarantee
that omitted files are irrelevant.

MIT licensed.
