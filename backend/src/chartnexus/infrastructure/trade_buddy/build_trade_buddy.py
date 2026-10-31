"""Composition bridge for Trade Buddy — assembles everything from the ``Container``.

The one module the ``trade_buddy`` context imports from infrastructure, which is
what keeps the context free of a static edge into the HTTP stack, the broker
adapter or another context. The independence contract exempts this single edge,
exactly as it does for messaging, report, hugin, mme100 and the rest.

Both sides are built here: the request-side ``TradeBuddyServices`` for the
routes, and ``build_watch_engine`` / ``build_feed`` for the background worker.
Keeping them together is deliberate — the engine the routes report on and the
engine the worker drives must be built from the same settings, and two builders
would eventually disagree about a threshold.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import Request

from chartnexus.contexts.trade_buddy.application.channels import (
    ConnectChannel,
    DisconnectChannel,
    GetChannels,
    LinkChat,
    SendChannelTest,
    SetChannelEnabled,
)
from chartnexus.contexts.trade_buddy.application.ports import (
    AlertSink,
    Clock,
    FeedHealth,
    LevelStore,
)
from chartnexus.contexts.trade_buddy.application.routing import AlertRouter, Notifier
from chartnexus.contexts.trade_buddy.application.use_cases import (
    ClearLevels,
    FireTestAlert,
    GetLevels,
    GetOverrides,
    SetLevels,
    SetLevelsCommand,
    SetOverrides,
    SetOverridesCommand,
)
from chartnexus.contexts.trade_buddy.application.watch import WatchEngine
from chartnexus.contexts.trade_buddy.domain.bands import (
    BandMultiples,
    BandPolicy,
    ResolvedBands,
    resolve_bands,
)
from chartnexus.contexts.trade_buddy.domain.budget import LevelBudget, WhatsAppBudget
from chartnexus.contexts.trade_buddy.domain.channel import AlertChannel
from chartnexus.contexts.trade_buddy.domain.events import AlertEvent, AlertKind
from chartnexus.contexts.trade_buddy.domain.level import LevelBands, LevelMark
from chartnexus.contexts.trade_buddy.domain.schedule import WatchWindow, parse_holidays
from chartnexus.contexts.trade_buddy.domain.state import LevelState, LevelWatcher
from chartnexus.infrastructure.brokers.fyers.rest_client import FyersRestClient
from chartnexus.infrastructure.notifications.telegram.client import TelegramClient
from chartnexus.infrastructure.notifications.whatsapp.callmebot import CallMeBotNotifier
from chartnexus.infrastructure.persistence.postgresql.repositories.trade_buddy.alert_channel_repository import (
    SqlAlchemyAlertChannelRepository,
)
from chartnexus.infrastructure.trade_buddy.atr_source import FyersAtrSource
from chartnexus.infrastructure.trade_buddy.broker_credentials import (
    ConfiguredCredentials,
    ConnectedBrokerCredentials,
)
from chartnexus.infrastructure.trade_buddy.clock import SystemTradeBuddyClock
from chartnexus.infrastructure.trade_buddy.json_level_store import JsonLevelStore
from chartnexus.infrastructure.trade_buddy.telegram_channel import TelegramAlertSender
from chartnexus.infrastructure.trade_buddy.telegram_notifier import TelegramNotifier
from chartnexus.infrastructure.transport.http.dependencies import get_container


@dataclass(frozen=True, slots=True)
class EngineSnapshot:
    """What ``GET /state`` reports. Assembled here so the route stays thin."""

    market_open: bool
    last_tick_at: datetime | None
    last_price: float | None
    whatsapp_used: int
    whatsapp_limit: int
    #: The bands in force, and whether they were scaled from ATR or fell
    #: back to points. The page shows both, because a resolved point value
    #: is the only form of a multiple anyone can actually feel.
    bands: ResolvedBands
    #: The session the levels were marked for, and whether that is today.
    #: Stale levels are watched by nobody until they are re-marked.
    marked_on: date | None
    levels_stale: bool
    levels: tuple[tuple[LevelWatcher, int], ...]


@dataclass(frozen=True, slots=True)
class WatchRow:
    """One instrument, compressed to what a glance needs.

    Deliberately not an `EngineSnapshot`: the strip answers "is anything
    happening anywhere", and six levels of detail per instrument would bury
    that under the thing it is meant to surface.
    """

    symbol: str
    #: True once levels are marked — which is also what makes it watched.
    watched: bool
    market_open: bool
    last_price: float | None
    last_tick_at: datetime | None
    levels_marked: int
    #: The level price is nearest to, and how far away in points.
    nearest_label: str | None
    nearest_distance: float | None
    #: The most urgent level state on this instrument, or `None` if all idle.
    attention: str | None
    #: Whether this instrument's bands are ATR-scaled or degraded to points.
    band_source: str
    #: True when levels exist but belong to an earlier session. Nothing is
    #: alerted on until they are re-marked.
    levels_stale: bool


#: Most urgent first. The strip shows one word per instrument, so it has to be
#: the one that would change what you do.
_URGENCY = (
    LevelState.BROKEN,
    LevelState.BREAK_PENDING,
    LevelState.TOUCHED,
    LevelState.APPROACHING,
)


@dataclass(slots=True)
class TradeBuddyServices:
    """The request side of Trade Buddy, wired for one authenticated request."""

    get_levels: GetLevels
    set_levels: SetLevels
    clear_levels: ClearLevels
    fire_test: FireTestAlert
    get_overrides: GetOverrides
    set_overrides: SetOverrides
    get_channels: GetChannels
    connect_channel: ConnectChannel
    link_chat: LinkChat
    test_channel: SendChannelTest
    set_channel_enabled: SetChannelEnabled
    disconnect_channel: DisconnectChannel
    _store: LevelStore
    _window: WatchWindow
    _clock: Clock
    _policy: BandPolicy
    _atr_source: Any
    _cooldown: timedelta
    _daily_cap: int
    _whatsapp: WhatsAppBudget

    @property
    def defaults(self) -> BandPolicy:
        """The global settings an override departs from, for the panel."""
        return self._policy

    @property
    def default_throttles(self) -> tuple[float, int]:
        """Cooldown minutes and daily cap, before any per-instrument override."""
        return self._cooldown.total_seconds() / 60.0, self._daily_cap

    async def watchlist(self, symbols: Sequence[str]) -> tuple[WatchRow, ...]:
        """Every offered instrument, whether or not it is marked.

        Unmarked ones are listed too — an index you forgot to mark is exactly
        the thing worth seeing, and omitting it would make the oversight
        invisible.
        """
        rows = []
        for symbol in symbols:
            snapshot = await self.engine_state(symbol)
            levels = [watcher for watcher, _ in snapshot.levels]
            nearest_label, nearest_distance = _nearest(levels, snapshot.last_price)
            rows.append(
                WatchRow(
                    symbol=symbol,
                    watched=bool(levels),
                    market_open=snapshot.market_open,
                    last_price=snapshot.last_price,
                    last_tick_at=snapshot.last_tick_at,
                    levels_marked=len(levels),
                    nearest_label=nearest_label,
                    nearest_distance=nearest_distance,
                    attention=_attention(levels),
                    band_source=snapshot.bands.source.value,
                    levels_stale=snapshot.levels_stale,
                )
            )
        return tuple(rows)

    async def engine_state(self, symbol: str) -> EngineSnapshot:
        """Live state as last persisted by the worker.

        Read from the store rather than from a shared in-memory engine: the API
        and the watcher are separate processes in a deployed environment, and a
        status route that only worked in local dev would be worse than none.
        """
        runtime_first = await self._store.load_runtime(symbol)
        overrides = await self._store.load_overrides(symbol)
        # The worker caches the session's ATR; reuse it rather than spending a
        # history call on every page poll.
        bands = resolve_bands(
            atr=runtime_first.atr,
            multiples=self._policy.multiples,
            fallback=self._policy.fallback,
            overrides=overrides.bands,
            confirm_hold_seconds=self._policy.confirm_hold_seconds,
        )

        marked = await self._store.load_marks(symbol)
        watchers = await self._store.load_watchers(symbol)
        if not watchers:
            watchers = tuple(
                LevelWatcher(symbol=symbol, mark=mark, bands=bands.bands) for mark in marked.marks
            )

        # The worker owns the live counters and this is a different process, so
        # the only honest source for them is what it last wrote to disk. Built
        # fresh and then restored, rather than reported as defaults: a route
        # that always says "3 alerts left" and "last tick: never" looks like an
        # answer while being no better than silence.
        runtime = runtime_first
        budget = build_level_budget_from(
            timedelta(minutes=overrides.cooldown_minutes)
            if overrides.cooldown_minutes is not None
            else self._cooldown,
            overrides.daily_alert_cap if overrides.daily_alert_cap is not None else self._daily_cap,
        )
        if runtime.level_budget:
            budget.restore(runtime.level_budget)
        whatsapp = WhatsAppBudget(limit=self._whatsapp.limit, window=self._whatsapp.window)
        whatsapp.reload(list(runtime.whatsapp_sends))

        now = self._clock.now()
        session = self._window.session_date(now)
        return EngineSnapshot(
            market_open=self._window.is_open(now),
            last_tick_at=runtime.last_tick_at,
            last_price=runtime.last_price,
            whatsapp_used=whatsapp.used(now),
            whatsapp_limit=whatsapp.limit,
            bands=bands,
            marked_on=marked.marked_on,
            levels_stale=marked.is_stale(session),
            levels=tuple((watcher, budget.remaining(watcher.mark.label)) for watcher in watchers),
        )


def _nearest(
    levels: Sequence[LevelWatcher], price: float | None
) -> tuple[str | None, float | None]:
    """The level price is closest to, and the gap in points."""
    if price is None or not levels:
        return None, None
    closest = min(levels, key=lambda w: abs(w.mark.price - price))
    return closest.mark.label, abs(closest.mark.price - price)


def _attention(levels: Sequence[LevelWatcher]) -> str | None:
    """The most urgent state across an instrument's levels."""
    present = {watcher.state for watcher in levels}
    for state in _URGENCY:
        if state in present:
            return state.value
    return None


# -- building blocks ---------------------------------------------------------


def _settings(container: Any) -> Any:
    return container.settings.trade_buddy


def build_fallback_bands(container: Any) -> LevelBands:
    """The point bands used only when ATR is unavailable."""
    tb = _settings(container)
    return LevelBands(
        touch=tb.touch_band_points,
        approach=tb.approach_band_points,
        break_buffer=tb.break_buffer_points,
        confirm_hold_seconds=tb.confirm_hold_seconds,
    )


def build_policy(container: Any) -> BandPolicy:
    """How bands are scaled. One builder, so the API and the worker agree."""
    tb = _settings(container)
    return BandPolicy(
        multiples=BandMultiples(
            touch=tb.touch_atr_multiple,
            approach=tb.approach_atr_multiple,
            break_buffer=tb.break_atr_multiple,
        ),
        fallback=build_fallback_bands(container),
        confirm_hold_seconds=tb.confirm_hold_seconds,
        atr_period=tb.atr_period,
    )


def build_channel_repository(container: Any) -> SqlAlchemyAlertChannelRepository:
    """Trade Buddy's own channel store, with its own AAD prefix.

    Reuses the messaging cipher — the algorithm is the same; what differs is
    the `trade_buddy:` binding, which is what stops a briefing bot's token
    decrypting if it is ever moved into this table.
    """
    return SqlAlchemyAlertChannelRepository(container.database, container.messaging_cipher)


def build_alert_sender(container: Any) -> TelegramAlertSender:
    """Verify/link/send for Trade Buddy's bot."""
    tb = _settings(container)
    api_base = container.settings.messaging.telegram_api_base
    return TelegramAlertSender(
        TelegramClient(
            container.http,
            api_base=api_base,
            timeout_seconds=tb.request_timeout_seconds,
        ),
        container.http,
        api_base=api_base,
        timeout_seconds=tb.request_timeout_seconds,
        chart_url=tb.chart_url or None,
    )


def build_credentials(container: Any) -> ConnectedBrokerCredentials:
    """Fyers credentials: the broker connected in the app, else the env pair.

    One builder, so the ATR fetch and the socket cannot end up authenticating
    as different accounts.
    """
    tb = _settings(container)
    token = tb.fyers_access_token.get_secret_value() if tb.fyers_access_token else ""
    override = ConfiguredCredentials(tb.fyers_app_id, token) if tb.fyers_app_id and token else None
    return ConnectedBrokerCredentials(container, override=override)


def build_atr_source(container: Any) -> FyersAtrSource:
    """The ATR feed.

    Always built: whether credentials exist is decided per call, because the
    broker can be connected after the watcher starts. An unresolvable fetch
    returns `None` and every instrument falls back to point bands — the
    degraded mode the page reports rather than hides.
    """
    tb = _settings(container)
    return FyersAtrSource(
        FyersRestClient(container.http, timeout_seconds=tb.request_timeout_seconds),
        build_credentials(container),
    )


def build_window(container: Any) -> WatchWindow:
    tb = _settings(container)
    return WatchWindow.from_config(
        tb.watch_open,
        tb.watch_close,
        parse_holidays(tb.holidays),
    )


def build_store(container: Any) -> JsonLevelStore:
    tb = _settings(container)
    return JsonLevelStore(
        directory=Path(tb.state_directory),
        # A placeholder shape for rebuilding watchers off disk; the engine
        # overwrites it with the session's resolved bands on load.
        bands=build_fallback_bands(container),
    )


async def build_notifiers(container: Any) -> tuple[Notifier | None, Notifier | None]:
    """Telegram and WhatsApp, or ``None`` for whichever is unconfigured.

    Absent credentials disable a channel rather than failing startup: running
    with Telegram only is a perfectly good configuration, and refusing to boot
    because WhatsApp is unset would make the optional channel mandatory.
    """
    tb = _settings(container)
    telegram: Notifier | None = None
    whatsapp: Notifier | None = None

    # The bot connected in the Trade Buddy panel wins. The env pair stays as
    # an override for a deployment with no UI — the same arrangement as the
    # broker credentials, and for the same reason: a token managed in two
    # places goes stale in one of them.
    connected = await build_channel_repository(container).find_any_ready(AlertChannel.TELEGRAM)
    if connected is not None and connected.target is not None:
        telegram = TelegramNotifier(
            container.http,
            bot_token=connected.secret,
            chat_id=connected.target,
            api_base=container.settings.messaging.telegram_api_base,
            timeout_seconds=tb.request_timeout_seconds,
            chart_url=tb.chart_url or None,
        )
    else:
        token = tb.telegram_bot_token.get_secret_value() if tb.telegram_bot_token else ""
        if token and tb.telegram_chat_id:
            telegram = TelegramNotifier(
                container.http,
                bot_token=token,
                chat_id=tb.telegram_chat_id,
                api_base=container.settings.messaging.telegram_api_base,
                timeout_seconds=tb.request_timeout_seconds,
                chart_url=tb.chart_url or None,
            )

    api_key = tb.whatsapp_api_key.get_secret_value() if tb.whatsapp_api_key else ""
    if api_key and tb.whatsapp_phone:
        whatsapp = CallMeBotNotifier(
            container.http,
            phone=tb.whatsapp_phone,
            api_key=api_key,
            timeout_seconds=tb.request_timeout_seconds,
        )
    return telegram, whatsapp


async def build_router(container: Any, *, clock: Clock | None = None) -> AlertRouter:
    tb = _settings(container)
    telegram, whatsapp = await build_notifiers(container)
    return AlertRouter(
        telegram=telegram,
        whatsapp=whatsapp,
        clock=clock or SystemTradeBuddyClock(),
        budget=WhatsAppBudget(
            limit=tb.whatsapp_limit_per_window,
            window=timedelta(hours=tb.whatsapp_window_hours),
        ),
        attempts=tb.send_attempts,
        backoff_seconds=tb.send_backoff_seconds,
    )


def build_level_budget_from(cooldown: timedelta, daily_cap: int) -> LevelBudget:
    """A budget from plain values, for the request side which has no container."""
    return LevelBudget(cooldown=cooldown, daily_cap=daily_cap)


def build_level_budget(container: Any) -> LevelBudget:
    tb = _settings(container)
    return LevelBudget(
        cooldown=timedelta(minutes=tb.cooldown_minutes),
        daily_cap=tb.daily_alert_cap,
    )


async def build_watch_engine(
    container: Any,
    symbol: str,
    *,
    sink: AlertSink | None = None,
    router: AlertRouter | None = None,
) -> WatchEngine:
    """The worker-side engine for one instrument.

    `router` is passed in when several instruments are watched at once: the
    WhatsApp budget is a per-account ceiling, not a per-instrument one, so
    three engines each holding their own would let the real send rate reach
    three times the configured limit.
    """
    tb = _settings(container)
    clock = SystemTradeBuddyClock()
    router = router or await build_router(container, clock=clock)
    return WatchEngine(
        symbol=symbol,
        policy=build_policy(container),
        atr_source=build_atr_source(container),
        window=build_window(container),
        store=build_store(container),
        sink=sink or router,
        clock=clock,
        budget=build_level_budget(container),
        stale_after_seconds=tb.stale_after_seconds,
        # The same object the router spends from, so what gets persisted is the
        # real window rather than a copy that drifts from it.
        whatsapp_budget=router.budget,
    )


async def build_feed(container: Any, sink: AlertSink) -> Any:
    """The live Fyers feed, wired to report its own health through the sink.

    Reports to the sink rather than to an engine because one socket now serves
    every watched instrument: a dropped connection is a fact about the feed,
    not about NIFTY, and routing it through one engine would both misattribute
    it and send it three times if each engine held its own feed.

    Imported lazily so that neither the API process nor the unit tests need the
    Fyers SDK present merely to build the rest of Trade Buddy.
    """
    # Deliberately lazy: hoisting this would make `fyers-apiv3` a hard import
    # requirement for the API process and for every unit test, when only the
    # background watcher ever opens a socket.
    from chartnexus.infrastructure.brokers.fyers.data_socket import (  # noqa: PLC0415
        FyersTickFeed,
    )

    tb = _settings(container)
    credentials = await build_credentials(container).fetch()
    if credentials is None:
        # Nothing connected. The caller treats this as "no feed this session"
        # and tries again next time, rather than opening a socket that cannot
        # authenticate and reconnecting against a wall.
        return None

    clock = SystemTradeBuddyClock()

    async def report(reason: str, detail: str) -> None:
        await sink.deliver_health(FeedHealth(reason=reason, detail=detail, at=clock.now()))

    return FyersTickFeed(
        access_token=credentials.joined,
        on_health=report,
        litemode=tb.litemode,
    )


# -- the request side --------------------------------------------------------


async def build_trade_buddy_services(request: Request) -> TradeBuddyServices:
    container = get_container(request)
    clock = SystemTradeBuddyClock()
    store = build_store(container)
    channels = build_channel_repository(container)
    sender = build_alert_sender(container)
    router = await build_router(container, clock=clock)
    return TradeBuddyServices(
        get_levels=GetLevels(store=store),
        set_levels=SetLevels(store=store, window=build_window(container), clock=clock),
        clear_levels=ClearLevels(store=store),
        fire_test=FireTestAlert(sink=router, clock=clock, store=store),
        get_overrides=GetOverrides(store=store),
        set_overrides=SetOverrides(store=store),
        get_channels=GetChannels(repository=channels),
        connect_channel=ConnectChannel(repository=channels, sender=sender, clock=clock),
        link_chat=LinkChat(repository=channels, sender=sender, clock=clock),
        test_channel=SendChannelTest(repository=channels, sender=sender),
        set_channel_enabled=SetChannelEnabled(repository=channels, clock=clock),
        disconnect_channel=DisconnectChannel(repository=channels),
        _store=store,
        _window=build_window(container),
        _clock=clock,
        _policy=build_policy(container),
        _atr_source=build_atr_source(container),
        _cooldown=timedelta(minutes=container.settings.trade_buddy.cooldown_minutes),
        _daily_cap=container.settings.trade_buddy.daily_alert_cap,
        _whatsapp=router.budget,
    )


__all__ = [
    "AlertEvent",
    "AlertKind",
    "EngineSnapshot",
    "LevelMark",
    "SetLevelsCommand",
    "SetOverridesCommand",
    "TradeBuddyServices",
    "build_feed",
    "build_trade_buddy_services",
    "build_watch_engine",
]
