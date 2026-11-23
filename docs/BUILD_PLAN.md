# Ten-day MVP build plan

Build window: 23 November–2 December 2026. Each implementation increment must
include a README update describing the behavior, a runnable example where
useful, validation results, and remaining limitations.

## Deliverables

| Day | Date | Increment | Acceptance evidence |
| --- | --- | --- | --- |
| 1 | 23 Nov | Validated model, endpoint, and agent records | Invalid input rejected; IDs, UTC dates, and JSON round trip tested |
| 2 | 24 Nov | SQLite inventory and CRUD API | Create/list/read/update/delete; restart persistence and missing-record cases |
| 3 | 25 Nov | Configuration declarations and rule engine | Authentication, exposure, transport, and permissions checks with unknown-state handling |
| 4 | 26 Nov | Persistent scans and actionable findings | Stable rule IDs, severity, evidence, remediation, scan IDs, and scan history |
| 5 | 27 Nov | Controlled injection and leakage evaluation | Synthetic vulnerable/control cases, reproducible outcomes, clear fixture-only limits |
| 6 | 28 Nov | JSON/Markdown reports and references | Deterministic export, severity summary, evidence links, OWASP/NIST references without compliance claims |
| 7 | 29 Nov | Simple local dashboard | Inventory → scan → findings → report flow, readable empty and error states |
| 8 | 30 Nov | Regression coverage and automated checks | Repeatable checks on pushes; boundary inputs, unknown states, and escaping covered |
| 9 | 1 Dec | Reproducible demo and packaging | Clean setup, synthetic seed data, container run, persistent data volume |
| 10 | 2 Dec | End-to-end verification and release polish | Full documented demo reproduced; tests pass; limitations and completed scope reconciled |

The order can adapt to evidence from the current repository. Keep each daily
increment focused, and prefer small, meaningful commits that leave the app usable.

## Completion criteria

- Validated inventory for models, endpoints, and agents survives a restart.
- A scan evaluates declared configuration and returns actionable findings.
- Unknown configuration remains unknown rather than becoming an automatic pass.
- Findings retain severity, rule ID, evidence, and remediation in scan history.
- Controlled synthetic injection/leakage cases run locally without paid services.
- A local dashboard and JSON/Markdown export expose the same scan results.
- The README describes installation, a complete synthetic demo, tests, and limits.
- Automated checks and the final end-to-end demo pass from a clean environment.

This MVP evaluates declared configuration and explicitly labelled synthetic
evaluation cases. It does not discover an organisation's entire AI estate,
certify compliance, or establish that a real LLM is secure. Network scanning and
live provider integration require a separately scoped implementation.

## Progress

- Day 1 implemented: inventory schemas, synthetic example, and nine passing
  validation tests. Example validation, existing health/schema checks, and the
  installed dependency check also passed on Python 3.12.
- Days 2–10 pending.
