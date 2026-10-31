"""Which alert goes to which channel, and what it says when it gets there.

The asymmetry is the design, not an accident of implementation. Telegram is
cheap, formatted and interactive, so it gets everything — including the
``WICK_REJECTED`` events whose entire value is letting the reader see that the
hold window rejected something. WhatsApp is a scarce, plain-text relay through a
third party that throttles, so it gets only the events worth spending budget on.

Rendering lives here too, beside the policy, because the two are coupled: the
WhatsApp text has to survive with no bold, no monospace and no buttons, and a
single shared template would end up written for the weaker channel.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from chartnexus.contexts.trade_buddy.application.ports import AlertSink, Clock, FeedHealth
from chartnexus.contexts.trade_buddy.domain.budget import WhatsAppBudget
from chartnexus.contexts.trade_buddy.domain.events import AlertEvent, AlertKind
from chartnexus.contexts.trade_buddy.domain.level import LevelRole

#: The only level events that may spend WhatsApp budget. Feed health is routed
#: there too, but through its own path — a dead feed is not a level event.
WHATSAPP_KINDS = frozenset(
    {
        AlertKind.BREAK_CONFIRMED,
        AlertKind.RECLAIMED,
        AlertKind.GAPPED_THROUGH,
    }
)

_HEADLINE: dict[AlertKind, str] = {
    AlertKind.APPROACHING: "approaching",
    AlertKind.TOUCHED: "touched",
    AlertKind.BREAK_CONFIRMED: "BROKEN",
    AlertKind.WICK_REJECTED: "wick rejected",
    AlertKind.RECLAIMED: "RECLAIMED",
    AlertKind.GAPPED_THROUGH: "GAPPED THROUGH",
}


class Notifier:
    """One delivery channel. Subclassed per provider.

    An ABC rather than a Protocol because the retry/backoff behaviour is shared
    and belongs in a base class — every channel here is an HTTP call that can
    fail transiently, and three copies of the same backoff loop would drift.
    """

    name: str = "notifier"
    #: Plain-text only channels get the unformatted renderer.
    rich: bool = True

    async def send(self, text: str) -> None:
        """Deliver ``text``. Raises on definitive failure."""
        raise NotImplementedError


@dataclass(slots=True)
class AlertRouter(AlertSink):
    """Applies the channel policy, then renders and sends.

    Telegram failing is reported but not fatal; WhatsApp being out of budget is
    expected and silent. The engine never learns which channels were used,
    because its correctness does not depend on it.
    """

    telegram: Notifier | None
    whatsapp: Notifier | None
    clock: Clock
    budget: WhatsAppBudget = field(default_factory=WhatsAppBudget)
    #: Per-send attempts before a channel is given up on for this alert.
    attempts: int = 3
    backoff_seconds: float = 0.5

    async def deliver(self, event: AlertEvent) -> None:
        if self.telegram is not None:
            await self._try(self.telegram, render(event, rich=True))

        if event.kind not in WHATSAPP_KINDS or self.whatsapp is None:
            return

        now = self.clock.now()
        if not self.budget.available(now):
            # Budget spent. Deliberately silent on WhatsApp and already
            # delivered on Telegram, which is the degraded mode working as
            # designed rather than a failure to report.
            return
        if await self._try(self.whatsapp, render(event, rich=False)):
            self.budget.record(now)

    async def deliver_health(self, health: FeedHealth) -> None:
        """Feed health reaches both channels: a dead watcher is the one thing
        that looks exactly like a quiet market, so it is worth the budget."""
        text = (
            f"Trade Buddy feed problem\n{health.reason}\n{health.detail}\n"
            f"{health.at.isoformat(timespec='seconds')}"
        )
        if self.telegram is not None:
            await self._try(self.telegram, f"<b>⚠ Feed problem</b>\n{health.detail}")
        if self.whatsapp is None:
            return
        now = self.clock.now()
        if self.budget.available(now) and await self._try(self.whatsapp, text):
            self.budget.record(now)

    async def _try(self, notifier: Notifier, text: str) -> bool:
        """Send with bounded exponential backoff. True when it got through."""
        delay = self.backoff_seconds
        for attempt in range(1, self.attempts + 1):
            try:
                await notifier.send(text)
                return True
            except Exception:
                if attempt == self.attempts:
                    return False
                await asyncio.sleep(delay)
                delay *= 2
        return False  # pragma: no cover — the loop always returns first


def render(event: AlertEvent, *, rich: bool) -> str:
    """One alert as text. ``rich`` selects Telegram HTML over plain WhatsApp.

    Both variants state the role flip explicitly on a confirmed break, because
    "R2 broken" and "R2 is now support" are the same fact and only the second
    one tells the reader what to do with it.
    """
    headline = _HEADLINE[event.kind]
    arrow = "▲" if event.distance > 0 else "▼"
    flip = ""
    if event.flipped:
        becomes = "support" if event.role_after is LevelRole.SUPPORT else "resistance"
        flip = f" — now acting as {becomes}"

    if rich:
        return (
            f"<b>{event.symbol} {event.label} {headline}</b>{flip}\n"
            f"Level <code>{event.level_price:,.2f}</code> · "
            f"price <code>{event.price:,.2f}</code> ({arrow} {abs(event.distance):.1f})\n"
            f"<i>{event.at.isoformat(timespec='seconds')}</i>"
        )
    return (
        f"{event.symbol} {event.label} {headline}{flip}. "
        f"Level {event.level_price:,.2f}, price {event.price:,.2f} "
        f"({arrow} {abs(event.distance):.1f} pts) "
        f"at {event.at.isoformat(timespec='seconds')}"
    )
