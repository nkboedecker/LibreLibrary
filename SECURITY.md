# Security policy

## Supported versions

During `0.x`, only the latest minor release gets security fixes. No release is supported yet, because `v0.1.0` hasn't been published.

## Report a vulnerability

Report vulnerabilities privately through [GitHub private vulnerability reporting](https://docs.github.com/en/code-security/how-tos/report-and-fix-vulnerabilities/privately-reporting-a-security-vulnerability): on this repository's **Security** tab, select **Report a vulnerability**.

Don't open a public issue for a security problem.

## Response targets

These are targets, not guarantees, because this is a volunteer project.

- **First response:** within 7 days.
- **Assessment:** within 14 days.
- **Fix for a confirmed critical or high-severity issue:** within 30 days.

Fixes ship in a new patch release. Published image tags are never overwritten.

## Plugins

Plugins run inside the server process with its full privileges, and an admin chooses which to install. Plugins from third-party libraries aren't reviewed by this project. Report a problem in a third-party plugin to its own maintainers.
