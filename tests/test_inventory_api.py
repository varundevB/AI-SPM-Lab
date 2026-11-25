"""API contracts and file persistence against isolated temporary databases."""

import sqlite3
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import create_app


class InventoryAPITests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.database = Path(self.directory.name) / "nested" / "inventory.sqlite3"
        self.application = create_app(self.database)
        self.client = TestClient(self.application)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def payload(self, **changes):
        return {"name": "Demo assistant", "asset_type": "agent", "owner": "Platform", **changes}

    def create(self, **changes):
        response = self.client.post("/assets", json=self.payload(**changes))
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_empty_inventory_and_database_creation(self):
        self.assertTrue(self.database.is_file())
        self.assertEqual(self.client.get("/assets").json(), [])

    def test_create_and_read_asset(self):
        response = self.client.post("/assets", json=self.payload(tags=["demo", "demo"]))
        self.assertEqual(response.status_code, 201)
        asset = response.json()
        self.assertEqual(response.headers["location"], f"/assets/{asset['id']}")
        self.assertEqual(asset["tags"], ["demo"])
        self.assertEqual(self.client.get(response.headers["location"]).json(), asset)

    def test_list_has_stable_pagination(self):
        first = self.create(name="First")
        second = self.create(name="Second")
        self.assertEqual(self.client.get("/assets?limit=1").json(), [first])
        self.assertEqual(self.client.get("/assets?limit=1&offset=1").json(), [second])
        self.assertEqual(self.client.get("/assets?offset=2").json(), [])

    def test_invalid_pagination_is_rejected(self):
        for query in ("limit=0", "limit=101", "offset=-1", "limit=invalid"):
            with self.subTest(query=query):
                self.assertEqual(self.client.get(f"/assets?{query}").status_code, 422)

    def test_replace_preserves_identity_and_resets_omitted_optional_fields(self):
        original = self.create(provider="synthetic", tags=["old"])
        response = self.client.put(
            f"/assets/{original['id']}", json=self.payload(name="Updated", owner="Operations")
        )
        self.assertEqual(response.status_code, 200)
        updated = response.json()
        self.assertEqual(updated["id"], original["id"])
        self.assertEqual(updated["created_at"], original["created_at"])
        self.assertEqual(updated["name"], "Updated")
        self.assertEqual(updated["owner"], "Operations")
        self.assertIsNone(updated["provider"])
        self.assertEqual(updated["tags"], [])
        self.assertEqual(self.client.get(f"/assets/{original['id']}").json(), updated)

    def test_delete_removes_record_and_returns_empty_response(self):
        asset = self.create()
        response = self.client.delete(f"/assets/{asset['id']}")
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.content, b"")
        self.assertEqual(self.client.get(f"/assets/{asset['id']}").status_code, 404)
        self.assertEqual(self.client.get("/assets").json(), [])

    def test_missing_records_return_404_and_put_does_not_create(self):
        path = f"/assets/{uuid4()}"
        responses = (
            self.client.get(path),
            self.client.put(path, json=self.payload()),
            self.client.delete(path),
        )
        for response in responses:
            self.assertEqual(response.status_code, 404)
            self.assertEqual(response.json(), {"detail": "Asset not found"})
        self.assertEqual(self.client.get("/assets").json(), [])

    def test_invalid_uuid_is_rejected_for_all_item_routes(self):
        path = "/assets/not-a-uuid"
        for response in (
            self.client.get(path),
            self.client.put(path, json=self.payload()),
            self.client.delete(path),
        ):
            self.assertEqual(response.status_code, 422)

    def test_validation_failure_does_not_create_or_modify_records(self):
        original = self.create()
        invalid = self.payload(asset_type="endpoint", endpoint_url=None)
        self.assertEqual(self.client.post("/assets", json=invalid).status_code, 422)
        self.assertEqual(
            self.client.put(f"/assets/{original['id']}", json=invalid).status_code, 422
        )
        self.assertEqual(self.client.get("/assets").json(), [original])

    def test_validation_errors_do_not_echo_rejected_secret_values(self):
        for payload in (
            self.payload(api_key="synthetic-secret"),
            self.payload(endpoint_url="https://user:synthetic-secret@example.invalid/v1"),
            self.payload(endpoint_url="https://example.invalid/v1?token=synthetic-secret"),
        ):
            with self.subTest(payload=payload):
                response = self.client.post("/assets", json=payload)
                self.assertEqual(response.status_code, 422)
                self.assertNotIn("synthetic-secret", response.text)
                self.assertTrue(response.json()["detail"])

    def test_client_cannot_set_server_identity(self):
        for changes in ({"id": str(uuid4())}, {"created_at": "2020-01-01T00:00:00Z"}):
            with self.subTest(changes=changes):
                self.assertEqual(
                    self.client.post("/assets", json=self.payload(**changes)).status_code, 422
                )

    def test_sql_looking_text_remains_data(self):
        name = "Robert'); DROP TABLE assets;--"
        asset = self.create(name=name)
        self.assertEqual(self.client.get(f"/assets/{asset['id']}").json()["name"], name)
        self.assertEqual(len(self.client.get("/assets").json()), 1)

    def test_create_replace_and_delete_survive_app_restart(self):
        with TestClient(create_app(self.database)) as before:
            original = before.post("/assets", json=self.payload()).json()
            removed = before.post("/assets", json=self.payload(name="Remove me")).json()
            updated = before.put(
                f"/assets/{original['id']}", json=self.payload(name="Persistent update")
            ).json()
            self.assertEqual(before.delete(f"/assets/{removed['id']}").status_code, 204)
        with TestClient(create_app(self.database)) as restarted:
            self.assertEqual(restarted.get("/assets").json(), [updated])
            self.assertEqual(restarted.get(f"/assets/{original['id']}").json(), updated)
            self.assertEqual(restarted.get(f"/assets/{removed['id']}").status_code, 404)

    def test_separate_database_paths_are_isolated(self):
        self.create()
        with TestClient(create_app(Path(self.directory.name) / "other.sqlite3")) as other:
            self.assertEqual(other.get("/assets").json(), [])

    def test_storage_errors_return_503_without_database_details(self):
        with patch.object(
            self.application.state.inventory, "list",
            side_effect=sqlite3.OperationalError("private-database-path"),
        ):
            response = self.client.get("/assets")
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("private-database-path", response.text)

    def test_health_and_interactive_documentation_remain_available(self):
        self.assertEqual(self.client.get("/health").json(), {"status": "ok"})
        self.assertEqual(self.client.get("/docs").status_code, 200)
        schema = self.client.get("/openapi.json").json()
        self.assertEqual(set(schema["paths"]["/assets"]), {"get", "post"})
        self.assertEqual(set(schema["paths"]["/assets/{asset_id}"]), {"get", "put", "delete"})
        self.assertEqual(set(schema["paths"]["/assets/{asset_id}/checks"]), {"get"})

    def test_configuration_persists_and_checks_are_available_after_restart(self):
        config = {"authentication_enabled": True, "internet_exposed": False, "permissions": ["read", "read"]}
        asset = self.create(endpoint_url="https://example.invalid/v1", security=config)
        self.assertEqual(asset["security"]["permissions"], ["read"])
        with TestClient(create_app(self.database)) as restarted:
            response = restarted.get(f"/assets/{asset['id']}/checks")
            self.assertEqual(response.status_code, 200)
            result = response.json()
            self.assertEqual(result["asset_id"], asset["id"])
            self.assertEqual(result["summary"], {"passed": 4, "failed": 0, "unknown": 0})
            self.assertEqual(restarted.get(f"/assets/{asset['id']}").json(), asset)

    def test_checks_keep_failures_and_unknowns_separate(self):
        asset = self.create(security={"authentication_enabled": False})
        response = self.client.get(f"/assets/{asset['id']}/checks")
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result["summary"], {"passed": 0, "failed": 1, "unknown": 3})
        failure = result["checks"][0]
        self.assertEqual(failure["severity"], "high")
        self.assertIs(failure["evidence"]["authentication_enabled"], False)
        self.assertTrue(failure["remediation"])
        self.assertEqual(self.client.get(f"/assets/{asset['id']}/checks").json(), result)

    def test_replacement_rechecks_controls_and_omitting_security_resets_to_unknown(self):
        asset = self.create(security={"authentication_enabled": True, "permissions": []})
        path = f"/assets/{asset['id']}"
        self.assertEqual(self.client.put(path, json=self.payload(security={"permissions": ["*"]})).status_code, 200)
        result = self.client.get(path + "/checks").json()
        self.assertEqual(result["summary"], {"passed": 0, "failed": 1, "unknown": 3})
        self.assertEqual(self.client.put(path, json=self.payload()).status_code, 200)
        self.assertEqual(self.client.get(path + "/checks").json()["summary"]["unknown"], 4)

    def test_checks_validate_uuid_and_report_missing_assets(self):
        self.assertEqual(self.client.get("/assets/invalid/checks").status_code, 422)
        self.assertEqual(self.client.get(f"/assets/{uuid4()}/checks").status_code, 404)

    def test_invalid_nested_controls_are_rejected_and_not_echoed(self):
        for config in (
            {"authentication_enabled": "false"}, {"internet_exposed": 0},
            {"permissions": ["superuser"]}, {"api_key": "synthetic-secret"},
        ):
            with self.subTest(config=config):
                response = self.client.post("/assets", json=self.payload(security=config))
                self.assertEqual(response.status_code, 422)
                self.assertNotIn("synthetic-secret", response.text)
        self.assertEqual(self.client.get("/assets").json(), [])

    def test_legacy_rows_load_without_migration_or_check_side_effects(self):
        asset = self.create()
        legacy = dict(asset)
        legacy.pop("security")
        encoded = json.dumps(legacy)
        with sqlite3.connect(self.database) as connection:
            connection.execute("UPDATE assets SET record = ? WHERE id = ?", (encoded, asset["id"]))
        connection.close()
        result = self.client.get(f"/assets/{asset['id']}/checks")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()["summary"], {"passed": 0, "failed": 0, "unknown": 4})
        with sqlite3.connect(self.database) as connection:
            stored = connection.execute("SELECT record FROM assets WHERE id = ?", (asset["id"],)).fetchone()[0]
            self.assertEqual(connection.execute("SELECT count(*) FROM assets").fetchone()[0], 1)
        connection.close()
        self.assertEqual(stored, encoded)


if __name__ == "__main__":
    unittest.main()
