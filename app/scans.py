"""Saved configuration evaluations and findings scoped to each observation."""

from datetime import datetime, timezone
from typing import Literal
from uuid import UUID, uuid4, uuid5

from pydantic import BaseModel, ConfigDict, Field

from app.checks import AssetChecks, CheckResult, CheckSummary, evaluate_asset
from app.models import Asset


class ScanRequest(BaseModel):
    """An optional empty body; scan data is always generated on the server."""

    model_config = ConfigDict(extra="forbid")


class Finding(CheckResult):
    id: UUID
    scan_id: UUID
    asset_id: UUID
    status: Literal["fail"] = "fail"
    severity: Literal["high", "medium"]
    remediation: str = Field(min_length=1)


class ScanSummary(BaseModel):
    id: UUID
    asset_id: UUID
    asset_name: str
    created_at: datetime
    policy_version: str
    basis: Literal["declared_configuration"]
    summary: CheckSummary
    finding_count: int = Field(ge=0)


class Scan(BaseModel):
    id: UUID
    asset_id: UUID
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    asset_snapshot: Asset
    evaluation: AssetChecks
    findings: list[Finding]

    def as_summary(self) -> ScanSummary:
        return ScanSummary(
            id=self.id, asset_id=self.asset_id, asset_name=self.asset_snapshot.name,
            created_at=self.created_at, policy_version=self.evaluation.policy_version,
            basis=self.evaluation.basis, summary=self.evaluation.summary,
            finding_count=len(self.findings),
        )


def build_scan(asset: Asset) -> Scan:
    """Copy the input and materialize findings only for failed checks."""
    snapshot = asset.model_copy(deep=True)
    evaluation = evaluate_asset(snapshot)
    scan_id = uuid4()
    findings = [
        Finding(
            **check.model_dump(), id=uuid5(scan_id, check.rule_id),
            scan_id=scan_id, asset_id=snapshot.id,
        )
        for check in evaluation.checks if check.status == "fail"
    ]
    return Scan(
        id=scan_id, asset_id=snapshot.id, asset_snapshot=snapshot,
        evaluation=evaluation, findings=findings,
    )
