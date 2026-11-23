# AI-SPM-Lab

AI Security Posture Management for AI applications, model endpoints, and agents.

AI-SPM-Lab is being developed to inventory AI assets, evaluate configuration
risks, and report actionable security findings with supporting evidence.

## Project status

The current API provides a health endpoint and interactive API documentation.
Validated Python inventory records for models, endpoints, and agents are now
implemented. Inventory API/storage, configuration scanning, and findings reports
are planned; no security scan runs yet.

## Quick start

Requires Python 3.10 or newer. From the repository directory on macOS or Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

On Windows PowerShell, create the environment with `py -m venv .venv`, then
activate it with `.venv\Scripts\Activate.ps1`. The remaining commands are the same.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | Application health |
| GET | `/docs` | Interactive API documentation |
| GET | `/openapi.json` | OpenAPI specification |

```bash
curl -i http://127.0.0.1:8000/health
```

Expected response: HTTP `200 OK` with:

```json
{"status":"ok"}
```

Open <http://127.0.0.1:8000/docs> to explore the API. Stop the server with `Ctrl+C`.
The health endpoint confirms application availability; it does not evaluate
security posture. The current application needs no external API credentials.

## Inventory record validation

`AssetCreate` validates user-supplied metadata. `Asset` adds a UUID and a UTC
creation time. The synthetic record in [`examples/asset.json`](examples/asset.json)
can be validated locally without contacting an endpoint:

```bash
python -c 'from pathlib import Path; from app.models import AssetCreate; print(AssetCreate.model_validate_json(Path("examples/asset.json").read_text()).model_dump_json(indent=2))'
```

- Required: `name`, `asset_type` (`model`, `endpoint`, or `agent`), and `owner`.
- `environment`: `development` (default), `staging`, or `production`.
- Optional: `endpoint_url`, `provider`, `model_name`, and up to ten tags.
- Endpoint assets require an HTTP(S) URL. Credentials, query strings, and
  fragments are rejected; store a base URL and never include secrets in metadata.
- Names, owners, providers, and model names are limited to 120 characters;
  tags to 40 characters. Surrounding whitespace is trimmed and duplicate tags
  are removed in their original order. Unknown fields are rejected.

These records describe assets. They do not verify endpoint reachability or
security, and the API does not persist them yet.

## Validation

After installing the requirements, run:

```bash
python -m unittest discover -s tests -v
```

The nine inventory tests cover input boundaries, credential-bearing URLs, collection
limits, independent record IDs/lists, UTC timestamps, and JSON serialization.

## Ten-day build

The MVP build runs from **23 November to 2 December 2026**. The detailed
[build plan and completion criteria](docs/BUILD_PLAN.md) track inventory,
configuration rules, findings, synthetic evaluations, reports, a dashboard,
automated checks, packaging, and final verification.

Every implementation increment includes an updated README. Features remain
marked as planned until their implementation and checks have been reviewed.

### Build log

| Date | Delivered | Verification |
| --- | --- | --- |
| 2026-11-23 | Validated asset records, synthetic example, ten-day MVP plan | 9 tests passed; example validated; existing health/schema checks passed; dependency check passed |

## Roadmap

- AI asset inventory with validated records for models, endpoints, and agents.
- Configuration checks for authentication, exposure, and permissions.
- Findings with severity, evidence, and remediation guidance.
- Controlled evaluation cases for prompt injection and data leakage.
- Reporting with references to relevant OWASP and NIST guidance.

## Repository structure

```text
app/
  __init__.py       Application package
  main.py           FastAPI application and health endpoint
  models.py         Validated inventory records
examples/asset.json Synthetic inventory metadata; no real credentials
tests/              Inventory validation checks
docs/BUILD_PLAN.md  Ten-day milestones and completion criteria
requirements.txt   Application dependencies
.gitignore         Local environments and secrets excluded from Git
README.md          Project overview and usage
```
