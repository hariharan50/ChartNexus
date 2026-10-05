"""GenerateHuginCall — builds the digest, generates a call, stamps track record, saves."""

from __future__ import annotations

import uuid
from decimal import Decimal

from chartnexus.contexts.hugin.application.generate_call import GenerateHuginCall
from chartnexus.contexts.hugin.domain.call import HuginCall
from chartnexus.contexts.hugin.domain.lesson import Lesson
from chartnexus.contexts.hugin.domain.observation import Bias
from chartnexus.shared_kernel.types.identifiers import TenantId

TENANT = TenantId(uuid.uuid4())


class _FakeStore:
    async def today(self, t, i):  # type: ignore[no-untyped-def]
        return ()

    async def history(self, t, i, d):  # type: ignore[no-untyped-def]
        return ()

    async def lessons_for(self, t, i, k):  # type: ignore[no-untyped-def]
        return (Lesson(dedup_key="pcr_flip", text="PCR flip leads", hits=2),)

    async def latest_observation(self, t, i):  # type: ignore[no-untyped-def]
        return None

    async def append_observation(self, o):  # type: ignore[no-untyped-def]
        raise NotImplementedError

    async def grade_previous(self, oid, *, grade, score, evidence):  # type: ignore[no-untyped-def]
        raise NotImplementedError

    async def upsert_lessons(self, t, ls):  # type: ignore[no-untyped-def]
        raise NotImplementedError

    async def all_lessons(self, t):  # type: ignore[no-untyped-def]
        return ()


class _FakeGenerator:
    available = True

    def __init__(self) -> None:
        self.seen_digest: str | None = None
        self.seen_track: Decimal | None = None

    async def generate(self, digest, instrument, track_hit_rate):  # type: ignore[no-untyped-def]
        self.seen_digest = digest
        self.seen_track = track_hit_rate
        return HuginCall(
            instrument=instrument,
            bias=Bias.BULLISH,
            target_zone="23,600-23,650",
            conviction=Decimal("0.7"),
            track_hit_rate=track_hit_rate,
            rationale="VWAP reclaim + PCR flip",
            entry="23,050",
            stop="22,950",
            target1="23,200",
        )


class _FakeCalls:
    def __init__(self) -> None:
        self.saved: list[HuginCall] = []

    async def append(self, tenant_id, call):  # type: ignore[no-untyped-def]
        self.saved.append(call)

    async def recent(self, tenant_id, instrument, limit):  # type: ignore[no-untyped-def]
        return tuple(self.saved)


async def test_generates_grounded_call_and_saves_it() -> None:
    generator = _FakeGenerator()
    calls = _FakeCalls()
    use_case = GenerateHuginCall(
        generator=generator,
        store=_FakeStore(),
        calls=calls,
        lessons_top_k=8,
        history_days=7,
    )

    call = await use_case(TENANT, "NIFTY")

    assert use_case.available is True
    assert call.bias is Bias.BULLISH
    assert call.entry == "23,050"
    assert len(calls.saved) == 1  # persisted
    # The generator saw HUGIN's memory digest, not raw market data.
    assert generator.seen_digest is not None
    assert "PCR flip leads" in generator.seen_digest
    # No graded history in the fake store -> track record is None (honest).
    assert generator.seen_track is None
    assert call.track_hit_rate is None
