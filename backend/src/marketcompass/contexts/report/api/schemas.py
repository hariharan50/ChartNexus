"""Wire contract for the report endpoints."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class _Schema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AvailabilityResponse(_Schema):
    #: Whether the LLM narrative is available (a key is configured). The report
    #: still renders without it (deterministic fallback prose), but the UI uses
    #: this to show/hide the "powered by MME100" state.
    available: bool


class EnrollmentResponse(_Schema):
    #: Whether the tenant has opted the scheduled daily report on (off by default).
    enabled: bool


class SetEnrollmentRequest(_Schema):
    enabled: bool
