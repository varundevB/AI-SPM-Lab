"""AI-SPM-Lab API application and persistent inventory routes."""

import os
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.checks import AssetChecks, evaluate_asset
from app.inventory import InventoryStore
from app.models import Asset, AssetCreate
from app.scans import Finding, Scan, ScanRequest, ScanSummary


def get_inventory(request: Request) -> InventoryStore:
    return request.app.state.inventory


Inventory = Annotated[InventoryStore, Depends(get_inventory)]


def create_app(database_path: str | Path | None = None) -> FastAPI:
    """Create an app with an independently configurable SQLite inventory."""
    path = database_path if database_path is not None else os.getenv(
        "AI_SPM_DB_PATH", "data/inventory.sqlite3"
    )

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        inventory = InventoryStore(path)
        inventory.initialize()
        application.state.inventory = inventory
        yield

    application = FastAPI(
        title="AI-SPM-Lab",
        description="AI Security Posture Management for AI applications.",
        version="0.4.0",
        lifespan=lifespan,
    )

    @application.exception_handler(RequestValidationError)
    async def invalid_request(_request: Request, error: RequestValidationError):
        # Omit rejected input values, which may contain accidentally pasted secrets.
        details = [
            {"loc": item["loc"], "msg": item["msg"], "type": item["type"]}
            for item in error.errors()
        ]
        return JSONResponse(status_code=422, content={"detail": details})

    @application.exception_handler(sqlite3.OperationalError)
    async def storage_unavailable(_request: Request, _error: sqlite3.OperationalError):
        return JSONResponse(
            status_code=503,
            content={"detail": "Inventory storage is temporarily unavailable"},
        )

    @application.get("/health", tags=["Health"])
    def health() -> dict[str, str]:
        """Confirm application availability; this does not assess security."""
        return {"status": "ok"}

    @application.post("/assets", response_model=Asset, status_code=201, tags=["Inventory"])
    def create_asset(payload: AssetCreate, response: Response, inventory: Inventory) -> Asset:
        asset = inventory.create(payload)
        response.headers["Location"] = f"/assets/{asset.id}"
        return asset

    @application.get("/assets", response_model=list[Asset], tags=["Inventory"])
    def list_assets(
        inventory: Inventory,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> list[Asset]:
        """List oldest records first, breaking timestamp ties by UUID."""
        return inventory.list(limit=limit, offset=offset)

    @application.get(
        "/assets/{asset_id}", response_model=Asset, tags=["Inventory"],
        responses={404: {"description": "Asset not found"}},
    )
    def read_asset(asset_id: UUID, inventory: Inventory) -> Asset:
        asset = inventory.get(asset_id)
        if asset is None:
            raise HTTPException(status_code=404, detail="Asset not found")
        return asset

    @application.get(
        "/assets/{asset_id}/checks", response_model=AssetChecks, tags=["Configuration checks"],
        responses={404: {"description": "Asset not found"}},
    )
    def check_asset(asset_id: UUID, inventory: Inventory) -> AssetChecks:
        """Evaluate declared configuration without probing endpoints or saving a scan."""
        asset = inventory.get(asset_id)
        if asset is None:
            raise HTTPException(status_code=404, detail="Asset not found")
        return evaluate_asset(asset)

    @application.put(
        "/assets/{asset_id}", response_model=Asset, tags=["Inventory"],
        responses={404: {"description": "Asset not found"}},
    )
    def replace_asset(asset_id: UUID, payload: AssetCreate, inventory: Inventory) -> Asset:
        """Replace metadata while preserving the UUID and creation timestamp."""
        asset = inventory.replace(asset_id, payload)
        if asset is None:
            raise HTTPException(status_code=404, detail="Asset not found")
        return asset

    @application.delete(
        "/assets/{asset_id}", status_code=204, tags=["Inventory"],
        responses={404: {"description": "Asset not found"}},
    )
    def delete_asset(asset_id: UUID, inventory: Inventory) -> Response:
        if not inventory.delete(asset_id):
            raise HTTPException(status_code=404, detail="Asset not found")
        return Response(status_code=204)

    @application.post(
        "/assets/{asset_id}/scans", response_model=Scan, status_code=201, tags=["Scans"],
        responses={404: {"description": "Asset not found"}},
    )
    def create_scan(
        asset_id: UUID, response: Response, inventory: Inventory,
        payload: ScanRequest | None = None,
    ) -> Scan:
        """Save a configuration snapshot, all check results, and failed-check findings."""
        scan = inventory.create_scan(asset_id)
        if scan is None:
            raise HTTPException(status_code=404, detail="Asset not found")
        response.headers["Location"] = f"/scans/{scan.id}"
        return scan

    @application.get("/scans", response_model=list[ScanSummary], tags=["Scans"])
    def list_scans(
        inventory: Inventory,
        asset_id: UUID | None = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> list[ScanSummary]:
        """List saved observations newest first, optionally filtered by asset UUID."""
        return inventory.list_scans(asset_id=asset_id, limit=limit, offset=offset)

    @application.get(
        "/scans/{scan_id}", response_model=Scan, tags=["Scans"],
        responses={404: {"description": "Scan not found"}},
    )
    def read_scan(scan_id: UUID, inventory: Inventory) -> Scan:
        scan = inventory.get_scan(scan_id)
        if scan is None:
            raise HTTPException(status_code=404, detail="Scan not found")
        return scan

    @application.get(
        "/scans/{scan_id}/findings", response_model=list[Finding], tags=["Scans"],
        responses={404: {"description": "Scan not found"}},
    )
    def read_findings(scan_id: UUID, inventory: Inventory) -> list[Finding]:
        scan = inventory.get_scan(scan_id)
        if scan is None:
            raise HTTPException(status_code=404, detail="Scan not found")
        return scan.findings

    return application


app = create_app()
