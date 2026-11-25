"""Policy boundaries and incomplete declarations must not become safe defaults."""

import unittest

from pydantic import ValidationError

from app.checks import evaluate_asset
from app.models import Asset, AssetCreate, SecurityConfiguration


class ConfigurationCheckTests(unittest.TestCase):
    def asset(self, **changes):
        return Asset(name="Demo", asset_type="agent", owner="Platform", **changes)

    def statuses(self, result):
        return {check.rule_id: check.status for check in result.checks}

    def test_missing_configuration_remains_unknown_for_every_rule(self):
        result = evaluate_asset(self.asset())
        self.assertEqual(result.summary.model_dump(), {"passed": 0, "failed": 0, "unknown": 4})
        self.assertTrue(all(check.status == "unknown" for check in result.checks))
        self.assertTrue(all(check.severity is None for check in result.checks))

    def test_https_does_not_imply_authentication_or_internal_access(self):
        result = evaluate_asset(self.asset(endpoint_url="https://localhost/v1"))
        self.assertEqual(self.statuses(result), {
            "AUTH-001": "unknown", "EXPOSURE-001": "unknown",
            "TRANSPORT-001": "pass", "PERMISSIONS-001": "unknown",
        })

    def test_explicit_controls_pass_the_declared_baseline(self):
        result = evaluate_asset(self.asset(
            endpoint_url="https://example.invalid/v1",
            security={"authentication_enabled": True, "internet_exposed": False, "permissions": ["read"]},
        ))
        self.assertEqual(result.summary.model_dump(), {"passed": 4, "failed": 0, "unknown": 0})
        self.assertTrue(all(check.remediation is None for check in result.checks))

    def test_declared_risks_include_evidence_severity_and_remediation(self):
        result = evaluate_asset(self.asset(
            endpoint_url="http://example.invalid/v1",
            security={"authentication_enabled": False, "internet_exposed": True, "permissions": ["read", "admin"]},
        ))
        self.assertEqual(result.summary.model_dump(), {"passed": 0, "failed": 4, "unknown": 0})
        self.assertTrue(all(check.severity and check.evidence and check.remediation for check in result.checks))
        self.assertIs(result.checks[0].evidence["authentication_enabled"], False)
        self.assertEqual(result.checks[3].evidence["permissions"], ["read", "admin"])

    def test_missing_value_and_false_are_distinct(self):
        result = evaluate_asset(self.asset(security={"authentication_enabled": False}))
        self.assertEqual(result.summary.model_dump(), {"passed": 0, "failed": 1, "unknown": 3})
        self.assertEqual(self.statuses(result)["EXPOSURE-001"], "unknown")

    def test_permissions_distinguish_unknown_empty_limited_and_privileged(self):
        for grants, expected in (
            (None, "unknown"), ([], "pass"), (["read", "write", "execute"], "pass"),
            (["admin"], "fail"), (["*"], "fail"), (["read", "*"], "fail"),
        ):
            with self.subTest(grants=grants):
                result = evaluate_asset(self.asset(security={"permissions": grants}))
                self.assertEqual(self.statuses(result)["PERMISSIONS-001"], expected)

    def test_non_boolean_flags_are_rejected_instead_of_coerced(self):
        for field in ("authentication_enabled", "internet_exposed"):
            for value in ("true", "false", 0, 1, [], {}):
                with self.subTest(field=field, value=value), self.assertRaises(ValidationError):
                    SecurityConfiguration(**{field: value})

    def test_unknown_fields_and_unsupported_permission_categories_are_rejected(self):
        for config in ({"api_key": "synthetic"}, {"permissions": ["superuser"]}, {"permissions": "read"}):
            with self.subTest(config=config), self.assertRaises(ValidationError):
                SecurityConfiguration(**config)

    def test_permissions_are_bounded_deduplicated_and_null_is_preserved(self):
        self.assertEqual(SecurityConfiguration(permissions=["read", "read"]).permissions, ["read"])
        self.assertIsNone(SecurityConfiguration(permissions=None).permissions)
        with self.assertRaises(ValidationError):
            SecurityConfiguration(permissions=["read"] * 21)

    def test_default_configurations_are_independent_and_old_records_load(self):
        first, second = self.asset(), self.asset()
        first.security.authentication_enabled = True
        self.assertIsNone(second.security.authentication_enabled)
        legacy = first.model_dump(mode="json", exclude={"security"})
        loaded = Asset.model_validate(legacy)
        self.assertEqual(evaluate_asset(loaded).summary.unknown, 4)
        self.assertIsNone(AssetCreate(name="Old", owner="Platform", asset_type="model").security.permissions)

    def test_repeated_evaluation_is_deterministic_and_does_not_change_asset(self):
        asset = self.asset(endpoint_url="https://example.invalid")
        before = asset.model_dump_json()
        first = evaluate_asset(asset)
        self.assertEqual(first, evaluate_asset(asset))
        self.assertEqual(asset.model_dump_json(), before)
        self.assertEqual(first.basis, "declared_configuration")
        self.assertEqual(first.policy_version, "1")


if __name__ == "__main__":
    unittest.main()
