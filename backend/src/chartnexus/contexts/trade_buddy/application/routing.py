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
import html
from dataclasses import dataclass, field
from datetime import datetime

from chartnexus.contexts.trade_buddy.application.ports import AlertSink, Clock, FeedHealth
from chartnexus.contexts.trade_buddy.domain.budget import WhatsAppBudget
from chartnexus.contexts.trade_buddy.domain.events import AlertEvent, AlertKind
from chartnexus.contexts.trade_buddy.domain.level import LevelRole
from chartnexus.contexts.trade_buddy.domain.schedule import to_ist

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
    expected and silent. Neither changes what the engine does next — its
    correctness still does not depend on where an alert landed — but
    :meth:`deliver` returns the channels that took it, because the history
    written from it is read by someone asking whether a break reached their
    phone or only Telegram, and nothing else can answer that afterwards.
    """

    telegram: Notifier | None
    whatsapp: Notifier | None
    clock: Clock
    budget: WhatsAppBudget = field(default_factory=WhatsAppBudget)
    #: Per-send attempts before a channel is given up on for this alert.
    attempts: int = 3
    backoff_seconds: float = 0.5

    async def deliver(self, event: AlertEvent) -> tuple[str, ...]:
        """Send, and report which channels actually took it.

        A channel that was tried and failed is *not* in the result: the tuple
        says what was delivered, not what was attempted, so a history entry
        reading "telegram" is evidence a message exists rather than evidence
        one was posted into a void.
        """
        used: list[str] = []
        if self.telegram is not None and await self._try(self.telegram, render(event, rich=True)):
            used.append("telegram")

        if event.kind not in WHATSAPP_KINDS or self.whatsapp is None:
            return tuple(used)

        now = self.clock.now()
        if not self.budget.available(now):
            # Budget spent. Deliberately silent on WhatsApp and already
            # delivered on Telegram, which is the degraded mode working as
            # designed rather than a failure to report.
            return tuple(used)
        if await self._try(self.whatsapp, render(event, rich=False)):
            self.budget.record(now)
            used.append("whatsapp")
        return tuple(used)

    async def deliver_health(self, health: FeedHealth) -> None:
        """Feed health reaches both channels: a dead watcher is the one thing
        that looks exactly like a quiet market, so it is worth the budget."""
        text = (
            f"Trade Buddy feed problem\n{health.reason}\n{health.detail}\n"
            f"{health.at.isoformat(timespec='seconds')}"
        )
        if self.telegram is not None:
            await self._try(self.telegram, render_health_telegram(health))
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
        return _render_telegram(event)
    return (
        f"{event.symbol} {event.label} {headline}{flip}. "
        f"Level {event.level_price:,.2f}, price {event.price:,.2f} "
        f"({arrow} {abs(event.distance):.1f} pts) "
        f"at {event.at.isoformat(timespec='seconds')}"
    )


@dataclass(frozen=True, slots=True)
class _Style:
    """How one alert kind looks on Telegram.

    ``verb`` completes the line under the headline ("R2 broken upward"); when
    it is ``None`` that line names the level's role instead ("R2 · resistance").
    ``directional`` kinds append "upward"/"downward" to the verb.
    """

    emoji: str
    title: str
    verb: str | None
    meaning: str
    directional: bool = False


_STYLE: dict[AlertKind, _Style] = {
    AlertKind.APPROACHING: _Style(
        "👀", "APPROACHING", None, "Price is nearing the level — get ready."
    ),
    AlertKind.TOUCHED: _Style("🎯", "TOUCHED", None, "Price is at the level now."),
    AlertKind.BREAK_CONFIRMED: _Style(
        "🚀",
        "BREAKOUT",
        "broken",
        "Price held beyond the level — the break is confirmed.",
        directional=True,
    ),
    AlertKind.WICK_REJECTED: _Style(
        "🕯️", "WICK REJECTED", "held", "Price poked through but closed back — the level held."
    ),
    AlertKind.RECLAIMED: _Style(
        "🔁", "RECLAIMED", "reclaimed", "Price came back across a broken level."
    ),
    AlertKind.GAPPED_THROUGH: _Style(
        "⚡",
        "GAPPED THROUGH",
        "gapped",
        "Price jumped past the level without trading at it.",
        directional=True,
    ),
}


def _when(moment: datetime) -> str:
    """``10:42:15 IST  ·  Thu 19 Nov``: the trader's clock, not UTC."""
    local = to_ist(moment)
    return f"{local:%H:%M:%S} IST  ·  {local:%a %d %b}"


def _render_telegram(event: AlertEvent) -> str:
    """One alert as a spaced Telegram card (HTML parse mode).

    Every user- or feed-supplied string is escaped: a ``<`` or ``&`` in a
    label would otherwise make Telegram reject the whole message, and a
    rejected alert is a lost alert.
    """
    style = _STYLE[event.kind]
    up = event.distance > 0
    symbol = html.escape(event.symbol)
    label = html.escape(event.label)

    emoji, title = style.emoji, style.title
    if event.kind is AlertKind.BREAK_CONFIRMED and not up:
        emoji, title = "🔻", "BREAKDOWN"

    if style.verb is None:
        sub = f"<code>{label}</code>  ·  {event.role_before.value}"
    else:
        direction = (" upward" if up else " downward") if style.directional else ""
        sub = f"<code>{label}</code> {style.verb}{direction}"

    arrow = "▲" if up else "▼"
    side = "above" if up else "below"
    lines = [
        f"{emoji} <b>{symbol}  ·  {title}</b>",
        sub,
        "",
        "<pre>"
        f"Level   {event.level_price:,.2f}\n"
        f"Price   {event.price:,.2f}\n"
        f"Move    {arrow} {abs(event.distance):.1f} pts {side}"
        "</pre>",
    ]
    if event.flipped:
        becomes = "support" if event.role_after is LevelRole.SUPPORT else "resistance"
        lines.append(f"🔄 <b>{label} is now acting as {becomes}</b>")
    lines += ["", f"💡 <i>{style.meaning}</i>", "", f"🕒 {_when(event.at)}"]
    return "\n".join(lines)


def render_health_telegram(health: FeedHealth) -> str:
    """The feed-problem card. The detail can carry exception text, so it is escaped."""
    return (
        "⚠️ <b>Trade Buddy  ·  Feed problem</b>\n\n"
        f"{html.escape(health.detail)}\n\n"
        f"🕒 {_when(health.at)}"
    )
