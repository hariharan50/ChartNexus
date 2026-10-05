"""HUGIN caller when no model is configured — import-safe without the extra."""

from __future__ import annotations

from decimal import Decimal

from chartnexus.contexts.hugin.domain.call import HuginCall


class UnavailableHuginCaller:
    available = False

    async def generate(
        self, digest: str, instrument: str, track_hit_rate: Decimal | None
    ) -> HuginCall:
        _ = (digest, instrument, track_hit_rate)
        raise RuntimeError("HUGIN calls are unavailable — no language model is configured.")
