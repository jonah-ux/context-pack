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

## See it work

The demo reports the bounded file set, byte count, and digest so another agent can verify the same pack:

```json
{"schema":"context-pack/v1","bytes":38,"files":["README.md","hello.py"],"sha256":"fdd85e8274d91d749c3ad18802483589da4272643eee9d6475c84d0f88c9a6a1"}
```

## Related tools

Use [Chatlens](https://github.com/jonah-ux/chatlens) to recover prior context, [Agent Eval Kit](https://github.com/jonah-ux/agent-eval-kit) to test a promptable command, and [Agent Resume](https://github.com/jonah-ux/agent-resume) to carry the exact repository identity forward.

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
