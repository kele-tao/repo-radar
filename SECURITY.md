# Security policy

## Supported versions

| Version | Supported |
| ------- | --------- |
| 1.x     | yes       |

## Reporting a vulnerability

repo-radar reads untrusted files but never executes them, never writes outside
the output path you give it, and makes no network calls. The most realistic
issues are therefore:

- a crafted file that makes a parser hang (regex backtracking, pathological AST),
- a path traversal in `report --out`,
- a false negative in the secret-detection rules.

Please open a private security advisory on GitHub or email the maintainer. Include
the smallest file that reproduces the problem and the command you ran. We aim to
answer within seven days. Do not open a public issue before a fix is available.

## Scope notes

The tool prints excerpts of the files it scans (finding details are truncated to
120 characters). Do not scan directories whose contents you are not allowed to
display in a terminal or an HTML report you share.
