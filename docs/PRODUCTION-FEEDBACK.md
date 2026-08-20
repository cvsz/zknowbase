# Production Feedback Intake and Triage

This is the operational contract for the v0.2.0 feedback cycle. Do not paste secrets, API keys, access tokens, credentials, raw document contents, or personal data into issues. Redact first and rotate any exposed credential.

## Intake minimum

Use the production-feedback issue form and include:

- affected zknowbase version, commit, deployment profile, and self-hosted environment shape;
- UTC timestamp and a correlation/request ID if available;
- symptom, expected behavior, observed behavior, and customer/tenant impact class;
- a sanitized reproduction, frequency, and whether the issue is deterministic;
- relevant metric names and bounded values (never credentials or document text);
- security, privacy, data-loss, availability, or compatibility concerns;
- whether the issue is a regression from the immutable v0.1.0 baseline.

Never identify a tenant by name in a public issue. Use an internal reference such as `tenant-ref-<random>` and keep the mapping outside GitHub.

## Severity rubric

| Severity | Meaning | Target action |
| --- | --- | --- |
| P0 | Active cross-tenant exposure, credential compromise, unrecoverable data loss, or broad outage | Private security escalation, containment immediately, release blocker |
| P1 | Material availability, integrity, DR, upgrade, or governed-contract failure | Triage within two business days, fix/evidence before next release |
| P2 | Reproducible degradation with workaround or limited tenant impact | Schedule with measurable acceptance criteria |
| P3 | Cosmetic, documentation, or low-risk improvement | Backlog and batch with related work |

Security-sensitive reports must follow `SECURITY.md`; do not disclose exploit details in a public issue.

## Triage record

Each issue should maintain these fields in its first maintainer comment:

```text
Triage owner:
Severity:
Affected version/commit:
Regression from v0.1.0: yes/no/unknown
Tenant impact class:
Security/privacy review:
Reproduction status:
Evidence link(s):
Decision: contain / fix / monitor / close
Next review date:
```

A report is not closed as fixed until the linked test, metric capture, runbook step, or release evidence can be replayed from a clean checkout. Production evidence must be sanitized, timestamped in UTC, and tied to an exact commit or immutable artifact.
