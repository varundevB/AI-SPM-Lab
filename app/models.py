"""Validated inventory records; declaring an asset never contacts its endpoint."""

from datetime import datetime, timezone
from typing import Annotated, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

ShortText = Annotated[str, Field(min_length=1, max_length=120)]
Tag = Annotated[str, Field(min_length=1, max_length=40)]


class AssetCreate(BaseModel):
    """Metadata supplied by an inventory owner. Do not include credentials."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: ShortText
    asset_type: Literal["model", "endpoint", "agent"]
    owner: ShortText
    environment: Literal["development", "staging", "production"] = "development"
    endpoint_url: HttpUrl | None = Field(default=None, max_length=2048)
    provider: ShortText | None = None
    model_name: ShortText | None = None
    tags: list[Tag] = Field(default_factory=list, max_length=10)

    @field_validator("endpoint_url")
    @classmethod
    def reject_embedded_secrets(cls, value: HttpUrl | None) -> HttpUrl | None:
        """Store the base URL only, excluding common credential-bearing parts."""
        if value is not None and (
            value.username is not None
            or value.password is not None
            or value.query is not None
            or value.fragment is not None
        ):
            raise ValueError("Use a base URL without credentials, query, or fragment")
        return value

    @field_validator("tags")
    @classmethod
    def unique_tags(cls, value: list[str]) -> list[str]:
        """Keep the first occurrence and preserve the owner's display order."""
        return list(dict.fromkeys(value))

    @model_validator(mode="after")
    def require_endpoint_url(self) -> "AssetCreate":
        if self.asset_type == "endpoint" and self.endpoint_url is None:
            raise ValueError("An endpoint asset requires endpoint_url")
        return self


class Asset(AssetCreate):
    """Stored inventory entry with generated identity and UTC creation time."""

    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
