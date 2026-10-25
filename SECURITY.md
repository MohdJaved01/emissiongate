# Security policy

EmissionGate is a pre-1.0 project built for a hackathon. **It is a demo, not for production use**, until
the 1.0 exit criteria in [docs/ENTERPRISE_READINESS.md](docs/ENTERPRISE_READINESS.md) are met. The PR
gate in particular reads code from pull requests; see [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md) for
what it defends against today and what is still open.

## Reporting a vulnerability

Please **do not open a public issue** for a security problem.

- Use GitHub's private vulnerability reporting: the **Security** tab of this repository →
  **Report a vulnerability**. This opens a draft security advisory visible only to maintainers.
- Include the affected version or commit, how to reproduce it, and the impact you expect.
- Do not include real credentials, customer data or personal data. Synthetic reproductions are best.

## What to expect

| Step | Target |
|---|---|
| Acknowledge the report | 3 working days |
| First assessment (accepted, needs info, or not a vulnerability) | 10 working days |
| Fix released for a critical issue | 7 days after assessment |
| Fix released for a high issue | 30 days after assessment |

Fixes are developed in a private fork or the draft advisory, released, and then disclosed in a GitHub
security advisory, with a CVE where one applies. Reporters are credited unless they ask not to be.

## Supported versions

| Version | Supported |
|---|---|
| `main` | yes — fixes land here first |
| 0.1.x (hackathon build) | no — upgrade to `main` |

Once releases are published, the latest minor release and the one before it receive security fixes.

## Scope

In scope: the `emissiongate` package, the reference workflows in this repository and in `estate-repo/`,
and the release artefacts once they exist. Out of scope: the synthetic demo estate's content, third-party
dependencies (report those upstream; tell us if EmissionGate's use of them is affected), and social
engineering.
