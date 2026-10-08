# AI-SPM-Lab

AI Security Posture Management for AI applications, model endpoints, and agents.

AI-SPM-Lab is being developed to inventory AI assets, evaluate configuration
risks, and report actionable security findings with supporting evidence.

## Project status

The current API provides a health endpoint and interactive API documentation.
Asset inventory, configuration scanning, and findings reports are planned.

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
requirements.txt   Application dependencies
.gitignore         Local environments and secrets excluded from Git
README.md          Project overview and usage
```

