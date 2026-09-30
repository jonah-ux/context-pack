# Releasing

This guide describes the maintainer release path for `context-pack`. Do not publish a release from an unreviewed or unverified worktree.

## Before the release

1. Confirm the intended changes are merged and the working tree is clean.
2. Update `version` in `pyproject.toml` and add a dated entry to `CHANGELOG.md`.
3. Run the tests on Python 3.11 and 3.12. Confirm the Ubuntu/macOS GitHub Actions matrix is green.
4. Build both distribution formats and inspect the artifacts:

   ```bash
   python -m pip install build
   python -m build
   python -m pip install --no-deps --target /tmp/context-pack-wheel dist/*.whl
   ```

   For an sdist validation, install the source archive into a separate clean environment or target directory and run its CLI help. Avoid validating an artifact from the source checkout: use a clean temporary directory so imports cannot accidentally resolve to the working tree.
5. Review the complete changelog entry, package metadata, and release notes. Confirm no secrets or local build artifacts are included.

## Tag and publish

After review, create an annotated tag matching the package version (for example, `v0.2.0`) on the verified commit and push the tag through the repository's normal reviewed workflow. Create a GitHub Release for that tag using the changelog as the starting point for release notes. Attach the wheel and source distribution produced from that exact tagged commit if distributing archives.

If publishing to PyPI is enabled later, configure and follow the repository's approved trusted-publishing workflow; do not put a long-lived PyPI token in source, workflow files, or local command history. Verify the published version and artifacts after publication.

## After release

- Confirm the GitHub Release points to the intended tag and includes the right artifacts.
- Install the published artifact in a fresh environment and verify the `context-pack` command starts.
- Record any follow-up or rollback action in the release notes. If an artifact is incorrect or unsafe, yank or supersede it using the package index's supported process; do not silently retag a published version.
