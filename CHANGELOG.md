# Changelog

## 0.2.0 - unreleased

- add redacted `context-pack/manifest/v1` provenance manifests with deterministic file digests
- add `verify` to detect changed source, tampered manifests, and modified rendered packs
- add authenticated `diff/v1` reports for comparing source selections with a fail-on-change mode
- keep output and manifest writes atomic and refuse symlink or hard-link aliases

## 0.1.0 - 2026-09-30

Initial focused release with a stable CLI contract and synthetic demo.
