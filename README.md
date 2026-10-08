# SentinelAI

A learn-by-building project in **AI Security Posture Management (AI-SPM)**.

The goal is to gradually build a tool that inventories AI application assets,
checks their configuration, and reports security findings with evidence and
suggested fixes. Each small pull request should demonstrate something learned.

**Current status: Day 1.** A local FastAPI application with one health endpoint.
Asset discovery, scanning, risk scoring, and AI integrations are future work.

## Run locally

Use Python 3.10 or newer. From the repository directory on macOS or Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

On Windows PowerShell, create the environment with `py -m venv .venv`, then
activate it with `.venv\Scripts\Activate.ps1`. The remaining commands are the same.

In a second terminal:

```bash
curl -i http://127.0.0.1:8000/health
```

Expected: HTTP `200 OK` and the JSON body:

```json
{"status":"ok"}
```

Interactive API documentation: <http://127.0.0.1:8000/docs>.
Stop the server with `Ctrl+C`.

The health endpoint only confirms that the application can respond. It does not
assess the security of any system. No API key, paid service, or cloud account is
needed for Day 1.

## Starter structure

```text
app/
  __init__.py       Python package
  main.py           FastAPI application and GET /health
requirements.txt   Application dependencies
.gitignore         Keeps local environments and secrets out of Git
README.md          Setup, roadmap, and learning checklist
```

## Learning roadmap

This is a suggested 12-week pace; progress is measured by working contributions.

| Weeks | Learn | Build and demonstrate |
| --- | --- | --- |
| 1–2 | HTTP, IP addresses, ports, DNS/TLS basics, Python, Git, Linux, and Docker basics | Run this API, inspect requests, then add a mock `/chat` route and an API-key-protected `/documents` route. Containerize it after local setup is understood. |
| 3–4 | Authentication vs. authorization, input validation, secrets, and API security | Add validation and tests for permitted and rejected requests using local sample data. |
| 5–6 | AI assets: models, endpoints, datasets, agents, and their dependencies | Load a small local JSON inventory and return it through an API. |
| 7–8 | Configuration checks, evidence, severity, and false positives | Build a first scanner for the sample inventory, such as flagging an endpoint declared to have no authentication. |
| 9–10 | Prompt injection, data leakage, least privilege, and AI threat modeling | Add controlled lab cases and document what each check can and cannot detect. |
| 11–12 | Prioritization, remediation, and OWASP/NIST guidance | Produce a readable findings report, map relevant findings to referenced guidance, and record a short demonstration. |

Future checks should run only against systems you own or are authorized to test.
Use synthetic data in examples and keep credentials out of commits.

## Day 1: understand the first contribution

- [ ] Run the application locally.
- [ ] Call `/health` and identify the HTTP status, headers, and JSON body.
- [ ] Open `/docs` and send the same request from the browser.
- [ ] Read `app/main.py` and explain what `@app.get("/health")` does.
- [ ] Review the Day 1 pull request and merge it when you understand the changes.

Learning reference: [FastAPI first steps](https://fastapi.tiangolo.com/tutorial/first-steps/).

## Day 2: the next small pull request

Add `POST /chat` with a required, non-empty `message` field and a deterministic
mock response. Use no external model yet. Show one successful request and one
invalid request, then explain request validation in the PR description.

For each later contribution, describe **what changed**, **what you learned**, and
**how you checked it**. Continue learning one feature at a time.
