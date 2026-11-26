"""Saved observations, history boundaries, and transactional consistency."""

import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app.main import create_app
from app.models import Asset
from app.scans import Scan, build_scan


class ScanAPITests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.database = Path(self.directory.name) / "inventory.sqlite3"
        self.client = TestClient(create_app(self.database))
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def create_asset(self, **changes):
        payload = {"name": "Demo", "asset_type": "agent", "owner": "Platform", **changes}
        response = self.client.post("/assets", json=payload)
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def create_scan(self, asset):
        response = self.client.post(f"/assets/{asset['id']}/scans")
        self.assertEqual(response.status_code, 201, response.text)
        return response

    def risky_asset(self):
        return self.create_asset(
            endpoint_url="http://example.invalid/v1",
            security={"authentication_enabled": False, "internet_exposed": True, "permissions": ["*"]},
        )

    def test_saved_scan_has_snapshot_and_actionable_findings(self):
        asset = self.risky_asset()
        response = self.create_scan(asset)
        scan = response.json()
        self.assertEqual(response.headers["location"], f"/scans/{scan['id']}")
        self.assertEqual(scan["asset_snapshot"], asset)
        self.assertEqual(scan["evaluation"]["summary"], {"passed": 0, "failed": 4, "unknown": 0})
        self.assertEqual(scan["evaluation"]["policy_version"], "1")
        self.assertEqual(len(scan["findings"]), 4)
        self.assertEqual(len({item["id"] for item in scan["findings"]}), 4)
        for finding in scan["findings"]:
            self.assertIsInstance(UUID(finding["id"]), UUID)
            self.assertEqual(finding["scan_id"], scan["id"])
            self.assertEqual(finding["asset_id"], asset["id"])
            self.assertEqual(finding["status"], "fail")
            self.assertTrue(finding["severity"] and finding["remediation"] and finding["evidence"])
        self.assertEqual(self.client.get(response.headers["location"]).json(), scan)
        self.assertEqual(
            self.client.get(response.headers["location"] + "/findings").json(), scan["findings"]
        )

    def test_unknown_controls_are_preserved_without_findings(self):
        scan = self.create_scan(self.create_asset()).json()
        self.assertEqual(scan["evaluation"]["summary"], {"passed": 0, "failed": 0, "unknown": 4})
        self.assertEqual(scan["findings"], [])
        self.assertEqual(self.client.get(f"/scans/{scan['id']}/findings").json(), [])

    def test_passing_declarations_do_not_create_findings(self):
        asset = self.create_asset(
            endpoint_url="https://example.invalid/v1",
            security={"authentication_enabled": True, "internet_exposed": False, "permissions": []},
        )
        scan = self.create_scan(asset).json()
        self.assertEqual(scan["evaluation"]["summary"]["passed"], 4)
        self.assertEqual(scan["findings"], [])

    def test_history_is_newest_first_paginated_and_asset_scoped(self):
        first = self.create_asset(name="First")
        second = self.create_asset(name="Second")
        old = self.create_scan(first).json()
        other = self.create_scan(second).json()
        newest = self.create_scan(first).json()
        history = self.client.get("/scans").json()
        self.assertEqual([row["id"] for row in history], [newest["id"], other["id"], old["id"]])
        self.assertNotIn("asset_snapshot", history[0])
        self.assertEqual(history[0]["asset_name"], "First")
        self.assertEqual(history[0]["finding_count"], 0)
        filtered = self.client.get(f"/scans?asset_id={first['id']}&limit=1&offset=1").json()
        self.assertEqual([row["id"] for row in filtered], [old["id"]])
        self.assertEqual(self.client.get(f"/scans?asset_id={uuid4()}").json(), [])

    def test_history_retains_original_snapshot_after_edit_and_deletion(self):
        asset = self.risky_asset()
        scan = self.create_scan(asset).json()
        path = f"/assets/{asset['id']}"
        updated = {"name": "Edited", "asset_type": "agent", "owner": "Operations"}
        self.assertEqual(self.client.put(path, json=updated).status_code, 200)
        self.assertEqual(self.client.get(path + "/checks").json()["summary"]["unknown"], 4)
        self.assertEqual(self.client.delete(path).status_code, 204)
        self.assertEqual(self.client.get(f"/scans/{scan['id']}").json(), scan)
        self.assertEqual(self.client.get(f"/scans?asset_id={asset['id']}").json()[0]["asset_name"], "Demo")
        self.assertEqual(self.client.post(path + "/scans").status_code, 404)

    def test_restarts_preserve_results_and_reads_never_reevaluate(self):
        asset = self.risky_asset()
        scan = self.create_scan(asset).json()
        with patch("app.scans.evaluate_asset", side_effect=RuntimeError("Must not reevaluate history")):
            with TestClient(create_app(self.database)) as restarted:
                self.assertEqual(restarted.get(f"/scans/{scan['id']}").json(), scan)
                self.assertEqual(restarted.get(f"/scans/{scan['id']}/findings").json(), scan["findings"])
                self.assertEqual(restarted.get("/scans").json()[0]["finding_count"], 4)

    def test_repeated_posts_create_separate_observations_with_stable_finding_ids(self):
        asset = self.risky_asset()
        first, second = self.create_scan(asset).json(), self.create_scan(asset).json()
        self.assertNotEqual(first["id"], second["id"])
        self.assertTrue({row["id"] for row in first["findings"]}.isdisjoint(
            {row["id"] for row in second["findings"]}
        ))
        self.assertEqual(self.client.get(f"/scans/{first['id']}").json()["findings"], first["findings"])

    def test_invalid_ids_missing_resources_and_pagination(self):
        self.assertEqual(self.client.post(f"/assets/{uuid4()}/scans").status_code, 404)
        for path in (f"/scans/{uuid4()}", f"/scans/{uuid4()}/findings"):
            self.assertEqual(self.client.get(path).status_code, 404)
        for path in ("/scans/invalid", "/scans/invalid/findings", "/scans?asset_id=invalid",
                     "/scans?limit=0", "/scans?limit=101", "/scans?offset=-1"):
            self.assertEqual(self.client.get(path).status_code, 422)
        self.assertEqual(self.client.post("/assets/invalid/scans").status_code, 422)
        self.assertEqual(self.client.get("/scans").json(), [])

    def test_clients_cannot_submit_scan_results_and_history_has_no_write_routes(self):
        asset = self.create_asset()
        for body in ({"id": str(uuid4())}, {"findings": []}, {"evaluation": {"summary": {"passed": 4}}}):
            self.assertEqual(self.client.post(f"/assets/{asset['id']}/scans", json=body).status_code, 422)
        self.assertEqual(self.client.get("/scans").json(), [])
        scan = self.client.post(f"/assets/{asset['id']}/scans", json={}).json()
        self.assertEqual(self.client.put(f"/scans/{scan['id']}", json={}).status_code, 405)
        self.assertEqual(self.client.delete(f"/scans/{scan['id']}").status_code, 405)

    def test_current_checks_do_not_save_scans(self):
        asset = self.risky_asset()
        self.assertEqual(self.client.get(f"/assets/{asset['id']}/checks").status_code, 200)
        self.assertEqual(self.client.get("/scans").json(), [])

    def test_failed_insert_leaves_no_partial_scan_and_recovery_is_possible(self):
        asset = self.risky_asset()
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute(
                "CREATE TRIGGER reject_scan BEFORE INSERT ON scans "
                "BEGIN SELECT RAISE(ABORT, 'synthetic insertion failure'); END"
            )
        with TestClient(create_app(self.database), raise_server_exceptions=False) as client:
            self.assertEqual(client.post(f"/assets/{asset['id']}/scans").status_code, 500)
        self.assertEqual(self.client.get("/scans").json(), [])
        self.assertEqual(self.client.get(f"/assets/{asset['id']}").json(), asset)
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute("DROP TRIGGER reject_scan")
        self.assertEqual(self.create_scan(asset).status_code, 201)

    def test_asset_write_cannot_interleave_with_snapshot_and_save(self):
        asset = self.risky_asset()
        changed = {**asset, "name": "Concurrent edit"}

        def blocked_writer(snapshot):
            with closing(sqlite3.connect(self.database, timeout=0.01)) as connection:
                with self.assertRaises(sqlite3.OperationalError):
                    connection.execute(
                        "UPDATE assets SET record = ? WHERE id = ?",
                        (json.dumps(changed), asset["id"]),
                    )
            return build_scan(snapshot)

        with patch("app.inventory.build_scan", side_effect=blocked_writer):
            scan = self.create_scan(asset).json()
        self.assertEqual(scan["asset_snapshot"], asset)
        self.assertEqual(self.client.get(f"/assets/{asset['id']}").json(), asset)

    def test_existing_inventory_database_is_upgraded_without_rewriting_assets(self):
        path = Path(self.directory.name) / "legacy.sqlite3"
        asset = Asset(name="Legacy", asset_type="model", owner="Platform")
        original = json.dumps(asset.model_dump(mode="json", exclude={"security"}))
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.execute("CREATE TABLE assets (id TEXT PRIMARY KEY, created_at TEXT NOT NULL, record TEXT NOT NULL)")
            connection.execute("INSERT INTO assets VALUES (?, ?, ?)", (str(asset.id), asset.created_at.isoformat(), original))
        with TestClient(create_app(path)) as legacy:
            response = legacy.post(f"/assets/{asset.id}/scans")
            self.assertEqual(response.status_code, 201)
            self.assertEqual(response.json()["evaluation"]["summary"]["unknown"], 4)
        with closing(sqlite3.connect(path)) as connection:
            self.assertEqual(connection.execute("SELECT record FROM assets").fetchone()[0], original)


class ScanSnapshotTests(unittest.TestCase):
    def test_snapshot_is_detached_and_timestamp_is_utc(self):
        asset = Asset(name="Original", asset_type="agent", owner="Platform", tags=["original"])
        scan = build_scan(asset)
        asset.name = "Edited"
        asset.tags.append("later")
        asset.security.authentication_enabled = True
        self.assertEqual(scan.asset_snapshot.name, "Original")
        self.assertEqual(scan.asset_snapshot.tags, ["original"])
        self.assertIsNone(scan.asset_snapshot.security.authentication_enabled)
        self.assertEqual(scan.created_at.utcoffset(), timedelta(0))
        self.assertEqual(Scan.model_validate_json(scan.model_dump_json()), scan)


if __name__ == "__main__":
    unittest.main()
