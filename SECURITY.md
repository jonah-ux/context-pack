# Security Policy

## Supported versions

Security fixes are intended for the latest released version. Users should upgrade to the newest release before reporting an issue against an older version.

## Reporting a vulnerability

Please do not report suspected vulnerabilities in a public issue. Use GitHub's private vulnerability reporting for this repository: **[Report a vulnerability](https://github.com/jonah-ux/context-pack/security/advisories/new)**. Include the affected version, a clear impact description, and safe reproduction steps. Do not include real credentials, customer data, or confidential repository content in a report.

If private reporting is unavailable, contact the repository maintainers through a private GitHub channel before sharing details publicly.

## Safe use

`context-pack` assembles local repository content into an output intended to be shared with a person or another tool. That content may include proprietary code, credentials, personal data, or other sensitive material. Ignore rules and size limits are not a secret-detection or access-control boundary; an explicitly selected file may still contain sensitive information. Review the complete generated pack before sharing, and limit the selection to files appropriate for the recipient.

The tool is designed to read repository content and Git metadata, not execute project code or send repository data to an external service. Treat generated packs as sensitive to the same degree as their source files.
