# Contributing

Contributions are welcome. Open an issue for a bug or proposed change, then submit a focused pull request. For security reports, follow [SECURITY.md](SECURITY.md) rather than opening a public issue.

## Development setup

- Python 3.11 or newer
- Git
- No runtime third-party dependencies; `pytest` is used for the test extra

Create an environment, install the project in editable mode, and run the tests:

```bash
python -m venv .venv
# Activate: source .venv/bin/activate (macOS/Linux)
# PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --editable ".[test]"
python -m pytest
```

## Pull requests

- Keep changes scoped and explain the user-visible behavior they affect.
- Add or update tests for behavior changes. Prefer synthetic temporary Git repositories and fixtures; tests should not depend on private source trees, network access, or provider credentials.
- Preserve deterministic output, explicit budget behavior, and visible exclusion reasons.
- Document user-facing option or format changes in the README and `CHANGELOG.md`.
- Run the test suite locally and ensure the GitHub Actions checks pass.
- Do not include secrets, private repository content, or generated build artifacts in a pull request.

A pull request should state what changed, why, and how it was verified. Maintainers handle versioning and releases; see [docs/releasing.md](docs/releasing.md).
