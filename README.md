# Bounded Context Pack Builder

![bounded context pack builder workflow](docs/header.svg)

**Build deterministic, budget-aware repository context for coding agents.**

## Install

```bash
pip install git+https://github.com/jonah-ux/context-pack.git@main
```

## Quick start

```bash
context-pack --help
```

The first release is intentionally small, offline-friendly, and easy to inspect. JSON output is designed for agents; diagnostics stay explicit.

## Development

```bash
python -m unittest discover -s tests
python -m build --sdist --wheel
python demos/demo.py
```

## Limits

Read the command help and [release guide](docs/releasing.md) before using this in automation. This project does not claim permissions, isolation, verification, or provider behavior beyond the output fields it can prove.

MIT licensed. Contributions and sanitized bug reports are welcome.
