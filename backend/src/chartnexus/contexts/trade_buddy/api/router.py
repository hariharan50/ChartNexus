"""Trade Buddy endpoints — mark the morning's levels, read the live watch.

Every route is authenticated. The watch itself runs in the background worker,
not here: these routes set what it watches and report what it has seen. There is
deliberately no route that starts or stops the engine — a watch that can be left
off by an errant click is a watch that silently misses a break.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from chartnexus.contexts.trade_buddy.api.dependencies import Services
from chartnexus.contexts.trade_buddy.api.schemas import (
    ChannelResponse,
    ChannelsResponse,
    ConnectChannelRequest,
    DefaultsResponse,
    EngineStateResponse,
    LevelPayload,
    LevelsResponse,
    LinkChatRequest,
    OverridesPayload,
    ResolvedBandsResponse,
    SetChannelEnabledRequest,
    SetLevelsRequest,
    SetSettingsRequest,
    SettingsResponse,
    TestAlertRequest,
    TestAlertResponse,
    WatcherStateResponse,
    WatchlistResponse,
    WatchRowResponse,
)
from chartnexus.contexts.trade_buddy.application.channels import ConnectCommand
from chartnexus.contexts.trade_buddy.application.routing import render
from chartnexus.contexts.trade_buddy.application.use_cases import (
    SetLevelsCommand,
    SetOverridesCommand,
)
from chartnexus.contexts.trade_buddy.domain.channel import AlertChannel
from chartnexus.contexts.trade_buddy.domain.instruments import (
    DEFAULT_SYMBOL,
    WATCHABLE,
    is_watchable,
    normalise,
)
from chartnexus.infrastructure.transport.http.dependencies import CurrentPrincipal

router = APIRouter(prefix="/trade-buddy", tags=["trade-buddy"])


def _watched_symbol(
    symbol: Annotated[str, Query(description="Index to act on", examples=list(WATCHABLE))] = (
        DEFAULT_SYMBOL
    ),
) -> str:
    """Validate and canonicalise the instrument on a query string.

    The write bodies already refuse an instrument this module does not watch.
    Without the same guard here a `GET ?symbol=RELIANCE` answered 200 with an
    empty state — reading as "no levels marked" when the truth is "never
    watched", and disagreeing with the PUT that would have rejected it.

    Normalises as well as validates, so `?symbol=nifty` works.
    """
    canonical = normalise(symbol)
    if not is_watchable(canonical):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"{canonical} is not watched. Trade Buddy covers {', '.join(WATCHABLE)}.",
        )
    return canonical


WatchedSymbol = Annotated[str, Depends(_watched_symbol)]


@router.get(
    "/levels",
    response_model=LevelsResponse,
    summary="The levels currently marked for an instrument",
)
async def get_levels(
    services: Services,
    _: CurrentPrincipal,
    symbol: WatchedSymbol,
) -> LevelsResponse:
    marked = await services.get_levels(symbol)
    return LevelsResponse(
        symbol=symbol,
        levels=[LevelPayload.of(mark) for mark in marked.marks],
        marked_on=marked.marked_on,
    )


@router.put(
    "/levels",
    response_model=LevelsResponse,
    summary="Replace the marked levels",
)
async def set_levels(
    request: SetLevelsRequest,
    services: Services,
    _: CurrentPrincipal,
) -> LevelsResponse:
    """Replace the marks for one instrument.

    Saved watcher states are dropped: they describe price's journey past the
    *old* levels, and resuming them against new marks would replay a session
    that never happened.
    """
    marks = await services.set_levels(
        SetLevelsCommand(
            symbol=request.symbol,
            marks=tuple(level.to_mark() for level in request.levels),
        )
    )
    return LevelsResponse(symbol=request.symbol, levels=[LevelPayload.of(m) for m in marks])


@router.delete(
    "/levels",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Clear the marked levels and any live state",
)
async def clear_levels(
    services: Services,
    _: CurrentPrincipal,
    symbol: WatchedSymbol,
) -> None:
    await services.clear_levels(symbol)


@router.get(
    "/state",
    response_model=EngineStateResponse,
    summary="Live engine state — what the watcher currently believes",
)
async def get_state(
    services: Services,
    _: CurrentPrincipal,
    symbol: WatchedSymbol,
) -> EngineStateResponse:
    """What the watch has seen so far today.

    ``market_open`` and ``last_tick_at`` together answer the question that
    matters most: is the silence because nothing has happened, or because
    nothing is running?
    """
    snapshot = await services.engine_state(symbol)
    return EngineStateResponse(
        symbol=symbol,
        market_open=snapshot.market_open,
        last_tick_at=snapshot.last_tick_at,
        last_price=snapshot.last_price,
        bands=ResolvedBandsResponse.of(snapshot.bands),
        marked_on=snapshot.marked_on,
        levels_stale=snapshot.levels_stale,
        whatsapp_used=snapshot.whatsapp_used,
        whatsapp_limit=snapshot.whatsapp_limit,
        levels=[
            WatcherStateResponse.of(watcher, alerts_remaining=remaining)
            for watcher, remaining in snapshot.levels
        ],
    )


@router.get(
    "/watchlist",
    response_model=WatchlistResponse,
    summary="Every offered instrument, compressed to what a glance needs",
)
async def get_watchlist(services: Services, _: CurrentPrincipal) -> WatchlistResponse:
    """All three indices at once.

    So the page can answer "is anything happening anywhere" without cycling the
    picker — and so an index you forgot to mark is visible rather than simply
    absent.
    """
    rows = await services.watchlist(WATCHABLE)
    return WatchlistResponse(
        instruments=[
            WatchRowResponse(
                symbol=row.symbol,
                watched=row.watched,
                market_open=row.market_open,
                last_price=row.last_price,
                last_tick_at=row.last_tick_at,
                levels_marked=row.levels_marked,
                nearest_label=row.nearest_label,
                nearest_distance=(
                    round(row.nearest_distance, 2) if row.nearest_distance is not None else None
                ),
                attention=row.attention,
                band_source=row.band_source,
                levels_stale=row.levels_stale,
            )
            for row in rows
        ]
    )


async def _settings(services: Services, symbol: str) -> SettingsResponse:
    """Assemble the panel's view of one instrument's alerting."""
    snapshot = await services.engine_state(symbol)
    overrides = await services.get_overrides(symbol)
    policy = services.defaults
    default_cooldown, default_cap = services.default_throttles

    # Staleness is deliberately not repeated here. `SettingsResponse` does not
    # carry it, and the page already states it once, loudly, above this panel —
    # a second copy beside the thresholds reads as a third thing to check.
    return SettingsResponse(
        symbol=symbol,
        bands=ResolvedBandsResponse.of(snapshot.bands),
        cooldown_minutes=(
            overrides.cooldown_minutes
            if overrides.cooldown_minutes is not None
            else default_cooldown
        ),
        daily_alert_cap=(
            overrides.daily_alert_cap if overrides.daily_alert_cap is not None else default_cap
        ),
        defaults=DefaultsResponse(
            touch_multiple=policy.multiples.touch,
            approach_multiple=policy.multiples.approach,
            break_multiple=policy.multiples.break_buffer,
            atr_period=policy.atr_period,
            confirm_hold_seconds=policy.confirm_hold_seconds,
            cooldown_minutes=default_cooldown,
            daily_alert_cap=default_cap,
            fallback_touch=policy.fallback.touch,
            fallback_approach=policy.fallback.approach,
            fallback_break_buffer=policy.fallback.break_buffer,
        ),
        overrides=OverridesPayload.of(overrides),
    )


@router.get(
    "/settings",
    response_model=SettingsResponse,
    summary="Alert thresholds for one instrument, resolved and as overrides",
)
async def get_settings(
    services: Services,
    _: CurrentPrincipal,
    symbol: WatchedSymbol,
) -> SettingsResponse:
    """What is in force, what the defaults are, and what has been overridden.

    All three, because a multiple alone is a number nobody can feel: the panel
    has to show "0.06 x ATR" *and* "= 42.1 pts on BANKNIFTY today" for the
    setting to be tunable rather than guessed at.
    """
    return await _settings(services, symbol)


@router.put(
    "/settings",
    response_model=SettingsResponse,
    summary="Replace one instrument's alert overrides",
)
async def set_settings(
    request: SetSettingsRequest,
    services: Services,
    _: CurrentPrincipal,
) -> SettingsResponse:
    """Set or clear overrides. A `null` field means "use the scaled default".

    The running watcher picks these up on its next session roll or restart;
    the response is resolved immediately so the panel can show what the new
    values come to in points.
    """
    await services.set_overrides(
        SetOverridesCommand(
            symbol=request.symbol,
            overrides=request.overrides.to_overrides(),
        )
    )
    return await _settings(services, request.symbol)


# -- alert channels ---------------------------------------------------------
#
# Trade Buddy's own bot, separate from the one under Settings -> Channels. Two
# bots rather than one because a level break mid-trade and a once-a-morning
# briefing want different notification settings on a phone, and silencing one
# must not silence the other.


@router.get(
    "/channels",
    response_model=ChannelsResponse,
    summary="Trade Buddy's alert channels",
)
async def get_channels(services: Services, principal: CurrentPrincipal) -> ChannelsResponse:
    """Every channel, connected or not.

    An unconnected channel is returned as an empty row rather than omitted, so
    the panel always has something to render and "not set up" is visible
    instead of absent.
    """
    connected = {c.channel: c for c in await services.get_channels(principal.user_id)}
    return ChannelsResponse(
        channels=[
            ChannelResponse.of(connected[channel])
            if channel in connected
            else ChannelResponse.empty(channel)
            for channel in AlertChannel
        ]
    )


@router.put(
    "/channels/telegram",
    response_model=ChannelResponse,
    summary="Save and verify the Trade Buddy bot token",
    responses={422: {"description": "Telegram rejected the token"}},
)
async def connect_telegram(
    request: ConnectChannelRequest,
    services: Services,
    principal: CurrentPrincipal,
) -> ChannelResponse:
    """Store the token, after Telegram confirms it.

    Verified before the write: a token the provider has already refused should
    never reach the database, or the panel shows a connection that cannot
    possibly deliver.
    """
    connection = await services.connect_channel(
        ConnectCommand(
            user_id=principal.user_id,
            tenant_id=principal.tenant_id,
            channel=AlertChannel.TELEGRAM,
            secret=request.secret.strip(),
        )
    )
    return ChannelResponse.of(connection)


@router.post(
    "/channels/telegram/link",
    response_model=ChannelResponse,
    summary="Link the chat the alerts go to",
)
async def link_telegram_chat(
    request: LinkChatRequest,
    services: Services,
    principal: CurrentPrincipal,
) -> ChannelResponse:
    """Resolve the chat id, or accept one typed in.

    Auto-detection reads whoever last messaged the bot. With `target` null and
    nobody having messaged it yet, the connection comes back unlinked rather
    than erroring — that is a normal first run, since a bot cannot open a
    conversation.
    """
    connection = await services.link_chat(
        principal.user_id, AlertChannel.TELEGRAM, target=request.target
    )
    return ChannelResponse.of(connection)


@router.post(
    "/channels/telegram/test",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Send a message to prove the channel works",
)
async def test_telegram(services: Services, principal: CurrentPrincipal) -> None:
    """Goes through the same sender the watcher uses, so a message arriving
    proves the token, the chat id and the formatting — not just that a row
    exists."""
    await services.test_channel(principal.user_id, AlertChannel.TELEGRAM)


@router.patch(
    "/channels/{channel_id}",
    response_model=ChannelResponse,
    summary="Turn a channel on or off",
)
async def set_channel_enabled(
    channel_id: str,
    request: SetChannelEnabledRequest,
    services: Services,
    principal: CurrentPrincipal,
) -> ChannelResponse:
    """Keeps the token and the chat, so switching back on is not a reconnect."""
    connection = await services.set_channel_enabled(
        principal.user_id, _alert_channel(channel_id), enabled=request.enabled
    )
    return ChannelResponse.of(connection)


@router.delete(
    "/channels/{channel_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Forget a channel's credentials entirely",
)
async def disconnect_channel(
    channel_id: str, services: Services, principal: CurrentPrincipal
) -> None:
    await services.disconnect_channel(principal.user_id, _alert_channel(channel_id))


def _alert_channel(value: str) -> AlertChannel:
    try:
        return AlertChannel(value.strip().lower())
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown channel {value!r}."
        ) from exc


@router.post(
    "/test-alert",
    response_model=TestAlertResponse,
    summary="Fire one synthetic alert through the real notifiers",
)
async def test_alert(
    request: TestAlertRequest,
    services: Services,
    _: CurrentPrincipal,
) -> TestAlertResponse:
    """Prove the channels and credentials work before a real break depends on them.

    Goes through the real router and the real policy, so a ``BREAK_CONFIRMED``
    test also exercises WhatsApp and spends a message from its budget.
    """
    event = await services.fire_test(request.symbol, request.kind)
    return TestAlertResponse(
        delivered=True,
        kind=event.kind,
        rendered=render(event, rich=False),
    )
