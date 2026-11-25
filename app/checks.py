"""Deterministic checks of declared configuration; no network probing."""

from collections import Counter
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.models import Asset


class CheckResult(BaseModel):
    rule_id: str
    title: str
    status: Literal["pass", "fail", "unknown"]
    severity: Literal["high", "medium"] | None
    message: str
    evidence: dict[str, str | bool | list[str] | None]
    remediation: str | None


class CheckSummary(BaseModel):
    passed: int = Field(ge=0)
    failed: int = Field(ge=0)
    unknown: int = Field(ge=0)


class AssetChecks(BaseModel):
    asset_id: UUID
    policy_version: Literal["1"] = "1"
    basis: Literal["declared_configuration"] = "declared_configuration"
    checks: list[CheckResult]
    summary: CheckSummary


def _result(
    rule_id: str,
    title: str,
    passes: bool | None,
    evidence: dict,
    severity: Literal["high", "medium"],
    messages: tuple[str, str, str],
    remediation: str,
) -> CheckResult:
    status = "unknown" if passes is None else "pass" if passes else "fail"
    message = messages[2] if passes is None else messages[0] if passes else messages[1]
    return CheckResult(
        rule_id=rule_id, title=title, status=status,
        severity=severity if status == "fail" else None,
        message=message, evidence=evidence,
        remediation=remediation if status == "fail" else None,
    )


def evaluate_asset(asset: Asset) -> AssetChecks:
    """Apply policy v1 in stable order and preserve incomplete configuration."""
    config = asset.security
    scheme = asset.endpoint_url.scheme if asset.endpoint_url is not None else None
    internal = None if config.internet_exposed is None else not config.internet_exposed
    restricted = None if config.permissions is None else not any(
        permission in {"admin", "*"} for permission in config.permissions
    )
    checks = [
        _result(
            "AUTH-001", "Authentication required", config.authentication_enabled,
            {"authentication_enabled": config.authentication_enabled}, "high",
            ("Authentication is declared enabled.", "Authentication is declared disabled.",
             "Authentication configuration is unknown."),
            "Require authentication at the asset boundary and update the declaration.",
        ),
        _result(
            "EXPOSURE-001", "Internal access baseline", internal,
            {"internet_exposed": config.internet_exposed}, "medium",
            ("The asset is declared internal.", "The asset is declared internet exposed.",
             "Internet exposure is unknown; it is not inferred from the URL."),
            "Restrict network exposure where possible; review and document any required public access.",
        ),
        _result(
            "TRANSPORT-001", "HTTPS endpoint configured",
            None if scheme is None else scheme == "https",
            {"endpoint_scheme": scheme}, "medium",
            ("An HTTPS endpoint URL is configured.", "A plain HTTP endpoint URL is configured.",
             "No endpoint URL is declared, so transport configuration is unknown."),
            "Configure an HTTPS endpoint URL; verify the deployed TLS configuration separately.",
        ),
        _result(
            "PERMISSIONS-001", "No administrative or wildcard grants", restricted,
            {"permissions": config.permissions}, "high",
            ("No administrative or wildcard grants are declared.",
             "Administrative or wildcard grants are declared.", "Permission grants are unknown."),
            "Replace admin or wildcard grants with the minimum permissions the asset needs.",
        ),
    ]
    counts = Counter(check.status for check in checks)
    return AssetChecks(
        asset_id=asset.id, checks=checks,
        summary=CheckSummary(passed=counts["pass"], failed=counts["fail"], unknown=counts["unknown"]),
    )
