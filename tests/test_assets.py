"""Inventory input boundaries, serialization, and isolation guarantees."""

import unittest
from datetime import timedelta
from uuid import UUID

from pydantic import ValidationError

from app.models import Asset, AssetCreate


class AssetValidationTests(unittest.TestCase):
    def payload(self, **changes):
        return {"name": "Support assistant", "asset_type": "agent", "owner": "Platform", **changes}

    def test_normalizes_whitespace_and_deduplicates_tags(self):
        asset = AssetCreate(**self.payload(name="  Support assistant  ", tags=[" demo ", "demo"]))
        self.assertEqual(asset.name, "Support assistant")
        self.assertEqual(asset.tags, ["demo"])

    def test_rejects_blank_required_text(self):
        for field in ("name", "owner"):
            with self.subTest(field=field), self.assertRaises(ValidationError):
                AssetCreate(**self.payload(**{field: "   "}))

    def test_rejects_unknown_fields_and_types(self):
        for change in ({"api_key": "synthetic-not-a-real-key"}, {"asset_type": "database"}, {"environment": "prod"}):
            with self.subTest(change=change), self.assertRaises(ValidationError):
                AssetCreate(**self.payload(**change))

    def test_endpoint_requires_http_url(self):
        for url in (None, "not-a-url", "file:///etc/passwd", "ftp://example.invalid/model"):
            with self.subTest(url=url), self.assertRaises(ValidationError):
                AssetCreate(**self.payload(asset_type="endpoint", endpoint_url=url))

    def test_rejects_credentials_queries_and_fragments(self):
        for url in (
            "https://user:synthetic@example.invalid/model",
            "https://example.invalid/model?api_key=synthetic",
            "https://example.invalid/model#synthetic",
        ):
            with self.subTest(url=url), self.assertRaises(ValidationError):
                AssetCreate(**self.payload(endpoint_url=url))

    def test_enforces_text_and_collection_limits(self):
        for change in ({"name": "a" * 121}, {"tags": ["a" * 41]}, {"tags": [str(i) for i in range(11)]}):
            with self.subTest(change=change), self.assertRaises(ValidationError):
                AssetCreate(**self.payload(**change))

    def test_model_can_be_registered_without_a_network_endpoint(self):
        asset = AssetCreate(**self.payload(asset_type="model", model_name="local-demo-model"))
        self.assertIsNone(asset.endpoint_url)

    def test_records_have_independent_ids_and_tag_lists(self):
        first, second = Asset(**self.payload()), Asset(**self.payload())
        self.assertIsInstance(first.id, UUID)
        self.assertNotEqual(first.id, second.id)
        first.tags.append("first-only")
        self.assertEqual(second.tags, [])
        self.assertEqual(first.created_at.utcoffset(), timedelta(0))

    def test_json_round_trip_keeps_record_identity(self):
        asset = Asset(**self.payload(asset_type="endpoint", endpoint_url="https://example.invalid/v1"))
        self.assertEqual(Asset.model_validate_json(asset.model_dump_json()), asset)


if __name__ == "__main__":
    unittest.main()
