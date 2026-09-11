# Security policy

## Reporting

Please report suspected vulnerabilities privately via GitHub's **Report a
vulnerability** button (Security tab) on
<https://github.com/gorkemguler/MetaCLS>, or by email to the address on
the repository owner's GitHub profile. Do not open a public issue for
anything that could expose users before a fix is out.

Please include: the MetaCLS version, how it was invoked (CLI / web /
API), a minimal file or request that triggers it, and what you observed
vs. expected. A CVE will be requested for confirmed issues.

## Scope

MetaCLS processes untrusted files. Findings of interest include:

- A crafted input that makes an engine **leave identifying metadata in
  the output** while reporting success.
- A crafted input that causes **path traversal / write outside the output
  directory**, resource exhaustion, or code execution.
- In the web UI / REST API: traversal via `run_id` / filename, or SSRF /
  auth bypass.

Out of scope: MetaCLS does not scrub document *body content* by design
(see the README); a comment's text or a form's default value surviving is
expected unless `--strip-form-values` / `--strip-office-authors` is used.
The web UI and API have **no authentication** by design and must be put
behind a proxy — that is documented, not a vulnerability.

## Supported versions

Only the latest release (and `main`) receive fixes while the project is
pre-1.0.
