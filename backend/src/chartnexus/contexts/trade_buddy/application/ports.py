"""Ports the Trade Buddy engine depends on.

* ``TickFeed`` — a live price stream. Satisfied by the Fyers WebSocket adapter
  and by ``ManualFeed``, which is what lets the engine be tested against a
  scripted market with no network and no clock.
* ``AlertSink`` — somewhere to deliver a rendered alert. Satisfied by the
  notifier router, which applies the per-channel policy.
* ``LevelStore`` — persistence for the marked levels *and* the live watcher
  states, so a restart mid-session neither loses the marks nor re-fires alerts
  for ground already covered.
* ``Clock`` — wall time and monotonic time, separately. The engine needs both
  and must be able to have either faked.

Protocols, not ABCs, matching every other context here: an adapter satisfies one
structurally and does not import the context to do it.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Protocol, runtime_checkable

from chartnexus.contexts.trade_buddy.domain.bands import AlertOverrides
from chartnexus.contexts.trade_buddy.domain.channel import AlertChannel, AlertConnection
from chartnexus.contexts.trade_buddy.domain.events import AlertEvent
from chartnexus.contexts.trade_buddy.domain.level import LevelMark, MarkSet
from chartnexus.contexts.trade_buddy.domain.state import LevelWatcher
from chartnexus.shared_kernel.types.identifiers import UserId


@dataclass(frozen=True, slots=True)
class Tick:
    """One price observation. The only shape the engine accepts."""

    symbol: str
    price: float
    at: datetime


@dataclass(frozen=True, slots=True)
class FeedHealth:
    """Why the feed is unhappy. Routed to every channel, including WhatsApp.

    Silence from a dead watcher is indistinguishable from silence from a quiet
    market, which is the whole reason this type exists.
    """

    reason: str
    detail: str
    at: datetime


@runtime_checkable
class TickFeed(Protocol):
    """A source of live ticks for a set of symbols."""

    async def subscribe(self, symbols: tuple[str, ...]) -> None:
        """Begin streaming the given symbols. Idempotent."""
        ...

    def ticks(self) -> AsyncIterator[Tick]:
        """Yield ticks as they arrive, until the feed is closed."""
        ...

    async def close(self) -> None:
        """Stop streaming and release the connection. Idempotent."""
        ...


@runtime_checkable
class AlertSink(Protocol):
    """Where alerts go once the engine has decided to send them."""

    async def deliver(self, event: AlertEvent) -> None:
        """Route one level event to whichever channels its policy allows."""
        ...

    async def deliver_health(self, health: FeedHealth) -> None:
        """Route a feed-health alert. Never throttled by the level budget."""
        ...


@dataclass(frozen=True, slots=True)
class RuntimeState:
    """Everything about the watch that is not a level, persisted beside them.

    Separate from the watcher states because it is read by a *different*
    process: the API answers ``GET /state`` without the worker's memory, so
    "when did a tick last arrive" and "how much budget is left" have to be on
    disk or the status route can only guess. Before this existed it reported
    ``last_tick_at: null`` and a full allowance forever, which is worse than
    reporting nothing — it looks like an answer.
    """

    #: Wall-clock time of the most recent tick, or ``None`` before the first.
    last_tick_at: datetime | None = None
    #: Price of the most recent tick. Persisted with the timestamp because the
    #: status page needs both to say anything useful: a time alone cannot show
    #: where price sits against the levels it is being compared to.
    last_price: float | None = None
    #: The IST session the watch is mid-way through. Load-bearing: gap
    #: settlement must happen once per *session*, not once per process. A
    #: restart at 14:00 that re-settled gaps would convert a resumed pending
    #: break into an instantly-confirmed GAPPED_THROUGH, bypassing the hold
    #: the store deliberately made it re-earn.
    session: date | None = None
    #: ``LevelBudget.snapshot()`` — per-level cooldowns and daily counts.
    level_budget: dict[str, object] = field(default_factory=dict)
    #: ``WhatsAppBudget.snapshot()`` — the rolling send window.
    whatsapp_sends: tuple[str, ...] = ()
    #: ATR(14) for this instrument, cached for the session. A daily figure,
    #: so fetching it once per session is correct and a restart should not
    #: re-fetch — nor silently fall back to unscaled points because the
    #: provider happened to be slow at that moment.
    atr: float | None = None


@runtime_checkable
class LevelStore(Protocol):
    """Durable storage for the marks, the live states and the runtime counters."""

    async def load_marks(self, symbol: str) -> MarkSet:
        """The levels marked for ``symbol``, with the session they were for.

        Returns an empty set when none are marked. The date rides with them
        because levels are a daily artefact and the watcher must be able to
        tell today's from Friday's.
        """
        ...

    async def save_marks(self, symbol: str, marks: tuple[LevelMark, ...], marked_on: date) -> None:
        """Replace the marked levels for ``symbol``, stamped with the session."""
        ...

    async def clear(self, symbol: str) -> None:
        """Drop the marks and any saved state for ``symbol``."""
        ...

    async def load_watchers(self, symbol: str) -> tuple[LevelWatcher, ...]:
        """Resume the saved watcher states, or empty if this is a fresh session."""
        ...

    async def save_watchers(self, symbol: str, watchers: tuple[LevelWatcher, ...]) -> None:
        """Persist the live states, so a restart resumes rather than restarts."""
        ...

    async def load_runtime(self, symbol: str) -> RuntimeState:
        """The persisted counters and last-tick time; defaults if never written."""
        ...

    async def save_runtime(self, symbol: str, state: RuntimeState) -> None:
        """Persist the counters and last-tick time."""
        ...

    async def load_overrides(self, symbol: str) -> AlertOverrides:
        """Per-instrument overrides, or an empty set."""
        ...

    async def save_overrides(self, symbol: str, overrides: AlertOverrides) -> None:
        """Replace this instrument's overrides."""
        ...


@dataclass(frozen=True, slots=True)
class BrokerCredentials:
    """What both Fyers paths need, in the shape each wants.

    The WebSocket takes the SDK's joined ``"APPID:TOKEN"``; the REST history
    call used for ATR takes the two separately. Joining is done here rather
    than by splitting a stored string, because an app id or token containing a
    colon would make the split ambiguous.
    """

    app_id: str
    access_token: str

    @property
    def joined(self) -> str:
        """The SDK's form for the data socket."""
        return f"{self.app_id}:{self.access_token}"


@runtime_checkable
class BrokerCredentialsSource(Protocol):
    """Where the watcher gets its Fyers credentials.

    Resolved per session rather than once per process: a Fyers access token
    expires daily, so a watcher that cached one at startup would be holding a
    dead token by the next morning without ever saying so.

    Returns ``None`` when nothing is connected, which is a normal state — the
    watcher then stays idle rather than retrying a connection it cannot make.
    """

    async def fetch(self) -> BrokerCredentials | None: ...


@runtime_checkable
class AtrSource(Protocol):
    """Average True Range for one instrument, used to scale the bands.

    A port rather than a direct call because the only implementation reaches
    the broker's history endpoint, and the engine must stay testable against a
    fixed number. Returning ``None`` is a legitimate answer — thin history, a
    provider outage — and the caller degrades to point bands and says so.
    """

    async def atr(self, symbol: str, *, period: int = 14) -> float | None:
        """Wilder's ATR over daily candles, or ``None`` if it cannot be computed."""
        ...


@runtime_checkable
class SecretCipher(Protocol):
    """Authenticated encryption for the bot token at rest.

    Same Protocol shape as the one in ``messaging`` and ``ai_settings``, and
    satisfied by the same ``AesGcmCipher`` — the difference is the AAD the
    repository binds with, not the algorithm.
    """

    def encrypt(self, plaintext: str, *, aad: str | None = None) -> str: ...

    def decrypt(self, ciphertext: str, *, aad: str | None = None) -> str: ...


@runtime_checkable
class AlertChannelRepository(Protocol):
    """Persistence for the per-(user, channel) alert connection."""

    async def find(self, user_id: UserId, channel: AlertChannel) -> AlertConnection | None: ...

    async def find_all(self, user_id: UserId) -> tuple[AlertConnection, ...]: ...

    async def find_any_ready(self, channel: AlertChannel) -> AlertConnection | None:
        """For the watcher, which has no request and therefore no user."""
        ...

    async def upsert(self, connection: AlertConnection) -> None: ...

    async def delete(self, user_id: UserId, channel: AlertChannel) -> None: ...


@dataclass(frozen=True, slots=True)
class ChannelIdentity:
    """What a channel reports about itself once its credentials verify — the
    bot's @username. Display only, but the thing that lets two bots be told
    apart at a glance."""

    label: str


@runtime_checkable
class AlertSenderPort(Protocol):
    """Verifying and sending on one channel. One implementation per provider."""

    async def verify(self, secret: str) -> ChannelIdentity:
        """Confirm the credentials with the provider; return its self-description.

        Raises ``ChannelVerificationError`` when the provider rejects them.
        """
        ...

    async def detect_target(self, secret: str) -> str | None:
        """Resolve a delivery target from recent activity — the chat id of the
        last person to message the bot — or ``None`` if nobody has yet."""
        ...

    async def send(self, secret: str, target: str, text: str) -> None:
        """Deliver ``text``. Raises on definitive failure."""
        ...


@runtime_checkable
class Clock(Protocol):
    def now(self) -> datetime:
        """Wall-clock time, timezone-aware. Used for display and for the cap."""
        ...

    def monotonic(self) -> float:
        """A second count that only increases.

        Separate from :meth:`now` on purpose: the break hold is measured against
        this, so an NTP correction mid-session cannot shorten or lengthen a
        twenty-second confirmation window.
        """
        ...
