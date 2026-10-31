"""Request and response shapes for the Trade Buddy routes."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from chartnexus.contexts.trade_buddy.domain.bands import (
    AlertOverrides,
    BandOverrides,
    ResolvedBands,
)
from chartnexus.contexts.trade_buddy.domain.channel import (
    AlertChannel,
    AlertConnection,
    is_valid_chat_id,
)
from chartnexus.contexts.trade_buddy.domain.events import AlertKind
from chartnexus.contexts.trade_buddy.domain.instruments import (
    DEFAULT_SYMBOL,
    WATCHABLE,
    is_watchable,
    normalise,
)
from chartnexus.contexts.trade_buddy.domain.level import LevelMark, LevelRole
from chartnexus.contexts.trade_buddy.domain.state import LevelState, LevelWatcher


class LevelPayload(BaseModel):
    """One marked level as the client sends it."""

    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=16, examples=["R2"])
    price: float = Field(gt=0, examples=[24650.0])
    role: LevelRole = Field(examples=[LevelRole.RESISTANCE])

    def to_mark(self) -> LevelMark:
        return LevelMark(label=self.label.strip(), price=self.price, role=self.role)

    @classmethod
    def of(cls, mark: LevelMark) -> LevelPayload:
        return cls(label=mark.label, price=mark.price, role=mark.role)


class SetLevelsRequest(BaseModel):
    """The morning's marks. Replaces whatever was there."""

    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(default=DEFAULT_SYMBOL, examples=list(WATCHABLE))
    levels: list[LevelPayload] = Field(min_length=1, max_length=12)

    @field_validator("symbol")
    @classmethod
    def _watchable(cls, value: str) -> str:
        canonical = normalise(value)
        if not is_watchable(canonical):
            raise ValueError(
                f"{canonical} is not watched. Trade Buddy covers {', '.join(WATCHABLE)}."
            )
        return canonical

    @field_validator("levels")
    @classmethod
    def _unique_labels(cls, levels: list[LevelPayload]) -> list[LevelPayload]:
        labels = [level.label.strip().upper() for level in levels]
        if len(set(labels)) != len(labels):
            raise ValueError("level labels must be unique")
        return levels


class LevelsResponse(BaseModel):
    symbol: str
    levels: list[LevelPayload]
    #: The session these were marked for. Null when never stamped.
    marked_on: date | None = None


class WatcherStateResponse(BaseModel):
    """One level's live state, as the terminal page renders it."""

    label: str
    level_price: float
    #: The role right now — flipped if the level has been broken.
    role: LevelRole
    state: LevelState
    #: True while a break is past the buffer but has not yet held long enough.
    break_pending: bool
    #: Observation alerts still available for this level today.
    alerts_remaining: int

    @classmethod
    def of(cls, watcher: LevelWatcher, *, alerts_remaining: int) -> WatcherStateResponse:
        return cls(
            label=watcher.mark.label,
            level_price=watcher.mark.price,
            role=watcher.role,
            state=watcher.state,
            break_pending=watcher.state is LevelState.BREAK_PENDING,
            alerts_remaining=alerts_remaining,
        )


class ResolvedBandsResponse(BaseModel):
    """The bands in force, and the story of where they came from.

    Both the multiple and the resolved points, because a multiple alone is a
    number nobody can feel: "0.06 x ATR" means nothing until it reads
    "= 42.1 pts on BANKNIFTY today".
    """

    touch: float
    approach: float
    break_buffer: float
    confirm_hold_seconds: float
    #: "atr" or "points".
    source: str
    #: The ATR the scaling used; null when unavailable.
    atr: float | None
    #: Set when a stored override was unusable and ignored.
    note: str | None = None

    @classmethod
    def of(cls, resolved: ResolvedBands) -> ResolvedBandsResponse:
        return cls(
            touch=round(resolved.bands.touch, 2),
            approach=round(resolved.bands.approach, 2),
            break_buffer=round(resolved.bands.break_buffer, 2),
            confirm_hold_seconds=resolved.bands.confirm_hold_seconds,
            source=resolved.source.value,
            atr=round(resolved.atr, 2) if resolved.atr is not None else None,
            note=resolved.note,
        )


class EngineStateResponse(BaseModel):
    """Everything the page needs to show whether the watch is actually running."""

    symbol: str
    #: False outside 09:15-15:20 IST, at weekends, and on configured holidays.
    market_open: bool
    #: None until the first tick of the session arrives.
    last_tick_at: datetime | None
    #: Last traded price, so the page can show where price sits.
    last_price: float | None
    #: How the bands were derived, and what they resolved to.
    bands: ResolvedBandsResponse
    #: The session the levels were marked for, and whether that is today.
    #: Stale levels are not alerted on at all — re-mark them.
    marked_on: date | None
    levels_stale: bool
    #: WhatsApp sends used in the rolling four-hour window, and the ceiling.
    whatsapp_used: int
    whatsapp_limit: int
    levels: list[WatcherStateResponse]


class WatchRowResponse(BaseModel):
    """One instrument on the watchlist strip."""

    symbol: str
    #: Marked levels are what make an instrument watched.
    watched: bool
    market_open: bool
    last_price: float | None
    last_tick_at: datetime | None
    levels_marked: int
    nearest_label: str | None
    nearest_distance: float | None
    #: The most urgent level state here, or null when everything is idle.
    attention: LevelState | None
    #: "atr" when the bands are scaled to this instrument, "points" when ATR
    #: was unavailable and it fell back — a degraded mode the page shows.
    band_source: str
    #: Levels exist but are from an earlier session; nothing is alerted on.
    levels_stale: bool


class WatchlistResponse(BaseModel):
    instruments: list[WatchRowResponse]


class OverridesPayload(BaseModel):
    """Per-instrument overrides. `null` means "use the scaled default"."""

    model_config = ConfigDict(extra="forbid")

    touch: float | None = Field(default=None, gt=0)
    approach: float | None = Field(default=None, gt=0)
    break_buffer: float | None = Field(default=None, gt=0)
    confirm_hold_seconds: float | None = Field(default=None, ge=0)
    #: Zero is meaningful here — it means no cooldown at all.
    cooldown_minutes: float | None = Field(default=None, ge=0)
    daily_alert_cap: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _ordered(self) -> OverridesPayload:
        """Refuse a pair that would be thrown away at watch time.

        Only checkable when *both* are overridden: against a scaled value the
        comparison needs an ATR this layer has no reason to fetch, and
        `resolve_bands` reports that case instead.
        """
        if self.touch is not None and self.approach is not None and self.touch > self.approach:
            raise ValueError(
                f"touch ({self.touch}) must not exceed approach ({self.approach}); "
                "price would register TOUCHED before it ever registered APPROACHING"
            )
        return self

    def to_overrides(self) -> AlertOverrides:
        return AlertOverrides(
            bands=BandOverrides(
                touch=self.touch,
                approach=self.approach,
                break_buffer=self.break_buffer,
                confirm_hold_seconds=self.confirm_hold_seconds,
            ),
            cooldown_minutes=self.cooldown_minutes,
            daily_alert_cap=self.daily_alert_cap,
        )

    @classmethod
    def of(cls, overrides: AlertOverrides) -> OverridesPayload:
        return cls(
            touch=overrides.bands.touch,
            approach=overrides.bands.approach,
            break_buffer=overrides.bands.break_buffer,
            confirm_hold_seconds=overrides.bands.confirm_hold_seconds,
            cooldown_minutes=overrides.cooldown_minutes,
            daily_alert_cap=overrides.daily_alert_cap,
        )


class DefaultsResponse(BaseModel):
    """The global settings an override departs from."""

    touch_multiple: float
    approach_multiple: float
    break_multiple: float
    atr_period: int
    confirm_hold_seconds: float
    cooldown_minutes: float
    daily_alert_cap: int
    #: The point bands used when ATR is unavailable.
    fallback_touch: float
    fallback_approach: float
    fallback_break_buffer: float


class SettingsResponse(BaseModel):
    """What the alert-settings panel renders."""

    symbol: str
    #: What is actually in force, resolved — the only form the reader can feel.
    bands: ResolvedBandsResponse
    #: The effective throttles, after any override.
    cooldown_minutes: float
    daily_alert_cap: int
    defaults: DefaultsResponse
    overrides: OverridesPayload


class SetSettingsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(default=DEFAULT_SYMBOL, examples=list(WATCHABLE))
    overrides: OverridesPayload

    @field_validator("symbol")
    @classmethod
    def _watchable(cls, value: str) -> str:
        canonical = normalise(value)
        if not is_watchable(canonical):
            raise ValueError(
                f"{canonical} is not watched. Trade Buddy covers {', '.join(WATCHABLE)}."
            )
        return canonical


class ChannelResponse(BaseModel):
    """One alert channel, as the settings panel renders it."""

    channel: AlertChannel
    #: True once a secret is stored, whether or not a chat is linked yet.
    configured: bool
    #: True when a send can actually happen right now.
    ready: bool
    verified: bool
    enabled: bool
    #: The bot's @username, so two bots are tellable apart at a glance.
    label: str | None
    #: The linked chat id. Not a secret.
    target: str | None
    #: First and last four characters only. A bot token is a bearer
    #: credential and never goes back over the wire in full.
    masked_secret: str | None

    @classmethod
    def of(cls, connection: AlertConnection) -> ChannelResponse:
        return cls(
            channel=connection.channel,
            configured=connection.configured,
            ready=connection.ready,
            verified=connection.verified,
            enabled=connection.enabled,
            label=connection.label,
            target=connection.target,
            masked_secret=connection.masked_secret,
        )

    @classmethod
    def empty(cls, channel: AlertChannel) -> ChannelResponse:
        """The not-yet-connected state, so the panel always has a row to draw."""
        return cls(
            channel=channel,
            configured=False,
            ready=False,
            verified=False,
            enabled=True,
            label=None,
            target=None,
            masked_secret=None,
        )


class ChannelsResponse(BaseModel):
    channels: list[ChannelResponse]


class ConnectChannelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    #: The bot token from @BotFather. Verified against Telegram before it is
    #: stored, so a token that cannot work never reaches the database.
    secret: str = Field(min_length=10, max_length=512)


class LinkChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    #: Leave null to auto-detect from whoever last messaged the bot. Supplied
    #: explicitly when nobody has yet — a bot cannot open a conversation.
    target: str | None = Field(default=None, max_length=64)

    @field_validator("target")
    @classmethod
    def _looks_like_a_chat_id(cls, value: str | None) -> str | None:
        """Refuse anything that is not a chat id.

        Without this a stray word is stored verbatim, the channel reads as
        Ready, and the first real alert fails with Telegram's unhelpful
        "chat not found" — long after the mistake was made.
        """
        if value is None or not value.strip():
            return None
        cleaned = value.strip()
        if not is_valid_chat_id(cleaned):
            raise ValueError(
                f"{cleaned!r} is not a chat id. Expected a number such as 123456789 "
                "(negative for a group), or a public @channelname. Leave it blank to "
                "detect it automatically after messaging the bot."
            )
        return cleaned


class SetChannelEnabledRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool


class TestAlertRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(default=DEFAULT_SYMBOL)
    kind: AlertKind = Field(
        default=AlertKind.TOUCHED,
        description=(
            "Which event to simulate. BREAK_CONFIRMED also exercises the WhatsApp "
            "path and spends budget; TOUCHED stays on Telegram."
        ),
    )


class TestAlertResponse(BaseModel):
    delivered: bool
    kind: AlertKind
    rendered: str
