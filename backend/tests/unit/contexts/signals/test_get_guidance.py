"""The use case around the pure pipeline: it reads, judges, and logs *changes*.

Fakes stand in for the market read and the repository so the dedup rule — don't
re-persist an unchanged call every poll — is pinned without a database.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from marketcompass.contexts.signals.application.get_guidance import GetGuidance
from marketcompass.contexts.signals.application.ports import GuidanceRecord
from marketcompass.contexts.signals.domain.inputs import MarketSnapshot
from marketcompass.contexts.signals.domain.models import Decision, Guidance, Provenance
from marketcompass.shared_kernel.types.identifiers import TenantId

TENANT = TenantId(uuid.uuid4())


class _FakeMarket:
    def __init__(self, snapshot: MarketSnapshot) -> None:
        self._snapshot = snapshot

    async def read(self, tenant_id: TenantId, symbol: str) -> MarketSnapshot:
        return self._snapshot


class _FakeRepo:
    def __init__(self, latest: GuidanceRecord | None = None) -> None:
        self._latest = latest
        self.saved: list[Guidance] = []

    async def latest(self, tenant_id: TenantId, symbol: str) -> GuidanceRecord | None:
        return self._latest

    async def save(self, tenant_id: TenantId, guidance: Guidance) -> GuidanceRecord:
        self.saved.append(guidance)
        record = _record(guidance)
        self._latest = record
        return record

    async def history(self, tenant_id: TenantId, symbol: str, *, limit: int) -> tuple[()]:
        return ()


def _record(guidance: Guidance) -> GuidanceRecord:
    return GuidanceRecord(
        generated_at=datetime(2026, 8, 7, 6, 0, tzinfo=UTC),
        symbol=guidance.symbol,
        decision=guidance.decision,
        confidence=guidance.confidence,
        score=guidance.score,
        provenance=guidance.provenance,
    )


def _flat_snapshot() -> MarketSnapshot:
    # No data → HOLD at zero confidence. Enough to drive the use case; the pure
    # pipeline's own correctness is covered in test_guider.
    return MarketSnapshot(symbol="NIFTY", spot=25_000.0, sources=(Provenance.LIVE,))


async def test_first_call_is_persisted() -> None:
    repo = _FakeRepo(latest=None)
    use_case = GetGuidance(market=_FakeMarket(_flat_snapshot()), repository=repo)

    guidance = await use_case(TENANT, "NIFTY")

    assert guidance.decision is Decision.HOLD
    assert len(repo.saved) == 1


async def test_unchanged_call_is_not_re_persisted() -> None:
    prior = GuidanceRecord(
        generated_at=datetime(2026, 8, 7, 5, 0, tzinfo=UTC),
        symbol="NIFTY",
        decision=Decision.HOLD,
        confidence=0,
        score=0.0,
        provenance=Provenance.LIVE,
    )
    repo = _FakeRepo(latest=prior)
    use_case = GetGuidance(market=_FakeMarket(_flat_snapshot()), repository=repo)

    await use_case(TENANT, "NIFTY")

    assert repo.saved == []
