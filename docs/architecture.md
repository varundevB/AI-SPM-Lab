# Inventory and scan architecture

## Components and boundaries

| Component | Responsibility |
| --- | --- |
| `app/main.py` | Application factory, startup, HTTP routes, pagination, and error responses |
| `app/models.py` | Validate asset metadata and represent UUIDs and UTC creation times |
| `app/inventory.py` | Parameterized SQLite queries, scan transactions, and record serialization |
| `app/checks.py` | Pure configuration rules, evidence, and separate pass/fail/unknown counts |
| `app/scans.py` | Asset snapshots, observation IDs, summaries, and failed-check findings |
| SQLite file | Durable inventory and scan records across restarts |

`create_app(database_path)` allows each application instance to use a separate
database. Without an explicit argument, it reads `AI_SPM_DB_PATH` or uses
`data/inventory.sqlite3`. Startup creates the parent directory and missing tables/indexes.
Importing the module alone does not create the database.

Each repository operation opens a short-lived SQLite connection. Writes commit
before the HTTP handler returns success, failed transactions roll back, and the
connection closes after the operation. The `assets` table stores a UUID primary
key, creation timestamp, and a JSON representation of the validated record.
No model endpoint is contacted during inventory operations.

## Create request

```mermaid
sequenceDiagram
    actor Client
    participant API as FastAPI and Pydantic
    participant Store as InventoryStore
    participant DB as SQLite file
    Client->>API: POST /assets with metadata
    alt Invalid metadata
        API-->>Client: 422 with error locations and messages
    else Valid metadata
        API->>Store: Create validated asset
        Store->>Store: Generate UUID and UTC creation time
        Store->>DB: Parameterized INSERT and commit
        alt Database operation fails
            DB-->>Store: Operational error
            Store-->>API: Storage error
            API-->>Client: 503 without database details
        else Record committed
            DB-->>Store: Success
            Store-->>API: Stored asset
            API-->>Client: 201 with asset and Location header
        end
    end
```

Rejected input values are omitted from validation responses. This prevents an
accidentally pasted credential in a rejected URL or unknown field from being
reflected in the error body. Metadata itself is not a secrets store.

## Replace and delete logic

```mermaid
flowchart TD
    Request["PUT or DELETE /assets/{asset_id}"] --> UUID{"Valid UUID?"}
    UUID -->|"No"| Invalid["422 validation error"]
    UUID -->|"Yes"| Method{"PUT request?"}
    Method -->|"Yes"| Body{"Valid replacement metadata?"}
    Body -->|"No"| Invalid
    Body -->|"Yes"| Existing{"Asset exists?"}
    Method -->|"No: DELETE"| Delete["Delete matching UUID"]
    Existing -->|"No"| Missing["404 asset not found"]
    Existing -->|"Yes"| Replace["Replace metadata; retain UUID and creation time"]
    Replace --> Updated{"Record still present when updated?"}
    Updated -->|"No"| Missing
    Updated -->|"Yes"| Commit["Commit update"]
    Commit --> Success["200 updated asset"]
    Delete --> Removed{"Record deleted?"}
    Removed -->|"No"| Missing
    Removed -->|"Yes"| Deleted["Commit; 204 empty response"]
```

A replacement never inserts a missing record. Optional fields omitted from
`PUT` reset to their schema defaults. Concurrent replacements use the last
successful write; version-based conflict detection is not implemented. Database
operational failures in either flow produce `503` rather than a success response.

## Configuration evaluation

`GET /assets/{asset_id}/checks` reads a stored asset and evaluates four rules in
stable order. Invalid UUIDs return `422`; missing assets return `404`. It neither
changes the asset nor persists results, and never calls a model endpoint.

```mermaid
flowchart TD
    Asset["Validated stored asset"] --> Rules["Evaluate each policy rule"]
    Rules --> Known{"Required declaration available?"}
    Known -->|"No"| Unknown["Unknown; retain missing evidence"]
    Known -->|"Yes"| Baseline{"Satisfies declared baseline?"}
    Baseline -->|"Yes"| Pass["Pass with declared evidence"]
    Baseline -->|"No"| Fail["Fail with severity, evidence, remediation"]
    Unknown --> Summary["Separate passed, failed, unknown counts"]
    Pass --> Summary
    Fail --> Summary
    Summary --> Response["Return current results; no scan stored"]
```

The nested `security` object stores strict nullable authentication/exposure flags
and nullable permission categories. Missing fields remain `null`; an empty
permissions list is a known declaration of no grants. Old JSON records without
`security` load with unknown controls without rewriting the stored record.
`PUT` still performs full replacement, so omitted security fields reset to unknown.

Transport uses only the declared URL scheme. Exposure is never inferred from a
hostname, and HTTPS never implies authentication. Policy version `1` expects
authentication, internal access, an HTTPS URL when one is declared, and no admin
or wildcard grants. A failure denotes a mismatch with that baseline, not a
confirmed deployed vulnerability. Only failed checks carry severity/remediation;
unknown controls stay visible and are never counted as passes.

## Saving an observation

`POST /assets/{asset_id}/scans` accepts no body or an empty JSON object. A scan is
built from the stored asset rather than client-supplied results. It saves a deep
copy of the asset, the policy version, all check results, their summary, and
findings for failed checks only. Scan timestamps are generated in UTC.

```mermaid
sequenceDiagram
    actor Client
    participant API as FastAPI
    participant Store as InventoryStore
    participant Rules as Snapshot and rule evaluation
    participant DB as SQLite file
    Client->>API: POST /assets/{asset_id}/scans
    API->>Store: Create saved observation
    Store->>DB: BEGIN IMMEDIATE and read asset
    alt Asset missing
        DB-->>Store: No record
        Store->>DB: End transaction without changes
        Store-->>API: No asset
        API-->>Client: 404 asset not found
    else Asset exists
        DB-->>Store: Stored metadata and declarations
        Store->>Rules: Snapshot and evaluate
        Rules-->>Store: All results and failed-check findings
        Store->>DB: INSERT scan record and COMMIT
        DB-->>Store: Saved
        Store-->>API: Scan with observation IDs
        API-->>Client: 201 with scan and Location header
    end
```

The asset read and scan insertion share one transaction. `BEGIN IMMEDIATE`
reserves the writer before the read, preventing another writer from changing
the asset between reading its declarations and saving the observation.
See [SQLite transaction behavior](https://www.sqlite.org/lang_transaction.html).
Operational storage failures return `503`; failed writes roll back and do not
return a successful scan response.

The `scans` table stores scan UUID, original asset UUID, UTC timestamp, and the
complete serialized observation. An index supports asset-scoped history ordered
by timestamp and UUID. Existing inventory rows are preserved when these tables
and indexes are created. Scans have no cascading dependency on inventory rows,
so deleting an asset leaves its past observations available.

## Reading history

`GET /scans` returns bounded, newest-first summaries, optionally filtered by
asset UUID. `GET /scans/{scan_id}` returns the complete stored observation;
`GET /scans/{scan_id}/findings` returns its failed-check findings. These reads
deserialize stored results and never invoke the current rule evaluator.

Findings retain the original rule ID, severity, evidence, and remediation. Each
has a UUID derived from its scan UUID and rule ID, so IDs stay stable within the
saved observation and differ across scans. Unknown controls remain in the saved
evaluation and cannot become findings or automatic passes. The API provides no
update/delete routes for saved scans and does not track a finding's remediation
state across observations.

## Scope

The inventory API is intended for local development and has no authentication
layer. Configuration checks and saved scans inspect owner declarations only.
Evaluation cases, reports, and a dashboard remain planned.
