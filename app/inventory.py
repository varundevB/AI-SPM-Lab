"""File-backed inventory storage with a short-lived connection per operation."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path
from uuid import UUID

from app.models import Asset, AssetCreate
from app.scans import Scan, ScanSummary, build_scan


class InventoryStore:
    """Persist validated asset records without contacting model endpoints."""

    def __init__(self, database_path: str | Path):
        self.path = Path(database_path).expanduser().resolve()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        with closing(sqlite3.connect(self.path, timeout=5.0)) as connection:
            with connection:
                yield connection

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS assets (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    record TEXT NOT NULL
                )"""
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS scans (
                    id TEXT PRIMARY KEY,
                    asset_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    record TEXT NOT NULL
                )"""
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS scans_asset_created "
                "ON scans (asset_id, created_at DESC, id DESC)"
            )

    def create(self, payload: AssetCreate) -> Asset:
        asset = Asset(**payload.model_dump())
        with self._connection() as connection:
            connection.execute(
                "INSERT INTO assets (id, created_at, record) VALUES (?, ?, ?)",
                (str(asset.id), asset.created_at.isoformat(), asset.model_dump_json()),
            )
        return asset

    def list(self, limit: int = 50, offset: int = 0) -> list[Asset]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT record FROM assets ORDER BY created_at, id LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [Asset.model_validate_json(row[0]) for row in rows]

    def get(self, asset_id: UUID) -> Asset | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT record FROM assets WHERE id = ?", (str(asset_id),)
            ).fetchone()
        return None if row is None else Asset.model_validate_json(row[0])

    def replace(self, asset_id: UUID, payload: AssetCreate) -> Asset | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT record FROM assets WHERE id = ?", (str(asset_id),)
            ).fetchone()
            if row is None:
                return None
            previous = Asset.model_validate_json(row[0])
            asset = Asset(
                **payload.model_dump(), id=previous.id, created_at=previous.created_at
            )
            result = connection.execute(
                "UPDATE assets SET record = ? WHERE id = ?",
                (asset.model_dump_json(), str(asset_id)),
            )
            if result.rowcount == 0:
                return None
        return asset

    def delete(self, asset_id: UUID) -> bool:
        with self._connection() as connection:
            result = connection.execute(
                "DELETE FROM assets WHERE id = ?", (str(asset_id),)
            )
            return result.rowcount > 0

    def create_scan(self, asset_id: UUID) -> Scan | None:
        with self._connection() as connection:
            # Keep the asset read and saved observation in the same write transaction.
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT record FROM assets WHERE id = ?", (str(asset_id),)
            ).fetchone()
            if row is None:
                return None
            scan = build_scan(Asset.model_validate_json(row[0]))
            connection.execute(
                "INSERT INTO scans (id, asset_id, created_at, record) VALUES (?, ?, ?, ?)",
                (str(scan.id), str(scan.asset_id), scan.created_at.isoformat(), scan.model_dump_json()),
            )
        return scan

    def list_scans(
        self, asset_id: UUID | None = None, limit: int = 50, offset: int = 0
    ) -> list[ScanSummary]:
        statement = "SELECT record FROM scans"
        parameters: tuple = ()
        if asset_id is not None:
            statement += " WHERE asset_id = ?"
            parameters = (str(asset_id),)
        statement += " ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?"
        with self._connection() as connection:
            rows = connection.execute(statement, (*parameters, limit, offset)).fetchall()
        return [Scan.model_validate_json(row[0]).as_summary() for row in rows]

    def get_scan(self, scan_id: UUID) -> Scan | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT record FROM scans WHERE id = ?", (str(scan_id),)
            ).fetchone()
        return None if row is None else Scan.model_validate_json(row[0])
