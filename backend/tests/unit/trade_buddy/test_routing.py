"""The channel policy, the WhatsApp budget, and the two renderers.

The asymmetry is the point: WhatsApp is a scarce plain-text relay and must only
ever receive confirmed facts, while Telegram receives everything including the
wicks. A test that merely checked "an alert was sent" would pass with the policy
inverted, so every assertion here names the channel.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from chartnexus.contexts.trade_buddy.application.ports import FeedHealth
from chartnexus.contexts.trade_buddy.application.routing import (
    WHATSAPP_KINDS,
    AlertRouter,
    render,
)
from chartnexus.contexts.trade_buddy.domain.budget import WhatsAppBudget
from chartnexus.contexts.trade_buddy.domain.events import AlertKind
from chartnexus.contexts.trade_buddy.domain.level import LevelRole
from chartnexus.infrastructure.trade_buddy.clock import FakeClock
from tests.unit.trade_buddy.conftest import (
    SESSION_START,
    RecordingNotifier,
    alert_event as event,
)

pytestmark = pytest.mark.unit


def build_router(
    *,
    budget: WhatsAppBudget | None = None,
    attempts: int = 3,
    telegram_fails: int = 0,
    whatsapp_fails: int = 0,
) -> tuple[AlertRouter, RecordingNotifier, RecordingNotifier]:
    telegram = RecordingNotifier(name="telegram", rich=True, fail_times=telegram_fails)
    whatsapp = RecordingNotifier(name="whatsapp", rich=False, fail_times=whatsapp_fails)
    router = AlertRouter(
        telegram=telegram,
        whatsapp=whatsapp,
        clock=FakeClock(SESSION_START),
        budget=budget or WhatsAppBudget(),
        attempts=attempts,
        backoff_seconds=0.0,  # no real sleeping in tests
    )
    return router, telegram, whatsapp


class TestChannelPolicy:
    @pytest.mark.parametrize(
        "kind",
        [
            AlertKind.APPROACHING,
            AlertKind.TOUCHED,
            AlertKind.WICK_REJECTED,
            AlertKind.BREAK_CONFIRMED,
            AlertKind.RECLAIMED,
            AlertKind.GAPPED_THROUGH,
        ],
    )
    async def test_telegram_receives_every_kind(self, kind):
        router, telegram, _ = build_router()
        await router.deliver(event(kind))
        assert len(telegram.sent) == 1

    @pytest.mark.parametrize(
        "kind",
        [AlertKind.APPROACHING, AlertKind.TOUCHED, AlertKind.WICK_REJECTED],
    )
    async def test_whatsapp_never_receives_an_observation(self, kind):
        router, _, whatsapp = build_router()
        await router.deliver(event(kind))
        assert whatsapp.sent == []

    @pytest.mark.parametrize(
        "kind",
        [AlertKind.BREAK_CONFIRMED, AlertKind.RECLAIMED, AlertKind.GAPPED_THROUGH],
    )
    async def test_whatsapp_receives_confirmed_facts(self, kind):
        router, _, whatsapp = build_router()
        await router.deliver(event(kind))
        assert len(whatsapp.sent) == 1

    def test_the_policy_set_matches_the_confirmed_kinds(self):
        """Guards against the two lists drifting apart as kinds are added."""
        assert {
            AlertKind.BREAK_CONFIRMED,
            AlertKind.RECLAIMED,
            AlertKind.GAPPED_THROUGH,
        } == WHATSAPP_KINDS

    async def test_a_missing_channel_is_simply_skipped(self):
        """Telegram-only is a valid configuration, not a degraded one."""
        router = AlertRouter(
            telegram=None,
            whatsapp=RecordingNotifier(name="whatsapp", rich=False),
            clock=FakeClock(SESSION_START),
            backoff_seconds=0.0,
        )
        await router.deliver(event(AlertKind.BREAK_CONFIRMED))
        assert isinstance(router.whatsapp, RecordingNotifier)
        assert len(router.whatsapp.sent) == 1


class TestWhatsAppBudget:
    async def test_sends_stop_once_the_window_limit_is_reached(self):
        router, telegram, whatsapp = build_router(budget=WhatsAppBudget(limit=2))

        for _ in range(5):
            await router.deliver(event(AlertKind.BREAK_CONFIRMED))

        assert len(whatsapp.sent) == 2
        # Telegram keeps going — that is the degraded mode working as designed.
        assert len(telegram.sent) == 5

    async def test_the_window_rolls_forward(self):
        clock = FakeClock(SESSION_START)
        whatsapp = RecordingNotifier(name="whatsapp", rich=False)
        router = AlertRouter(
            telegram=None,
            whatsapp=whatsapp,
            clock=clock,
            budget=WhatsAppBudget(limit=1, window=timedelta(hours=4)),
            backoff_seconds=0.0,
        )

        await router.deliver(event(AlertKind.BREAK_CONFIRMED))
        await router.deliver(event(AlertKind.BREAK_CONFIRMED))
        assert len(whatsapp.sent) == 1

        clock.advance(timedelta(hours=4, minutes=1).total_seconds())
        await router.deliver(event(AlertKind.BREAK_CONFIRMED))
        assert len(whatsapp.sent) == 2

    async def test_a_failed_send_does_not_spend_budget(self):
        """Budget tracks what the provider actually received."""
        router, _, whatsapp = build_router(
            budget=WhatsAppBudget(limit=1), attempts=1, whatsapp_fails=1
        )

        await router.deliver(event(AlertKind.BREAK_CONFIRMED))
        assert whatsapp.sent == []
        assert router.budget.used(SESSION_START) == 0

        # The one allowance is still there for the next real break.
        whatsapp.fail_times = 0
        await router.deliver(event(AlertKind.BREAK_CONFIRMED))
        assert len(whatsapp.sent) == 1

    def test_restore_does_not_hand_back_a_fresh_allowance(self):
        """A restart must not reset a budget the provider is still counting."""
        original = WhatsAppBudget(limit=3)
        original.record(SESSION_START)
        original.record(SESSION_START)

        restored = WhatsAppBudget.restore(original.snapshot(), limit=3)

        assert restored.used(SESSION_START) == 2
        assert restored.available(SESSION_START)

    def test_restored_entries_outside_the_window_are_dropped(self):
        original = WhatsAppBudget(limit=1)
        original.record(SESSION_START)

        restored = WhatsAppBudget.restore(original.snapshot(), limit=1)
        later = SESSION_START + timedelta(hours=5)

        assert restored.used(later) == 0
        assert restored.available(later)


class TestRetry:
    async def test_a_transient_failure_is_retried(self):
        router, telegram, _ = build_router(attempts=3, telegram_fails=2)
        await router.deliver(event())
        assert len(telegram.sent) == 1
        assert telegram.attempts == 3

    async def test_retries_are_bounded(self):
        router, telegram, _ = build_router(attempts=3, telegram_fails=99)
        await router.deliver(event())
        assert telegram.sent == []
        assert telegram.attempts == 3

    async def test_telegram_failing_does_not_block_whatsapp(self):
        """The channels are independent; one dying must not silence the other."""
        router, telegram, whatsapp = build_router(attempts=1, telegram_fails=99)
        await router.deliver(event(AlertKind.BREAK_CONFIRMED))
        assert telegram.sent == []
        assert len(whatsapp.sent) == 1


class TestFeedHealthRouting:
    async def test_feed_health_reaches_both_channels(self):
        """A dead feed is the one thing that looks exactly like a quiet market."""
        router, telegram, whatsapp = build_router()
        await router.deliver_health(
            FeedHealth(reason="feed_stale", detail="No tick for 120s.", at=SESSION_START)
        )
        assert len(telegram.sent) == 1
        assert len(whatsapp.sent) == 1

    async def test_feed_health_respects_the_whatsapp_budget(self):
        router, telegram, whatsapp = build_router(budget=WhatsAppBudget(limit=0))
        await router.deliver_health(
            FeedHealth(reason="feed_stale", detail="No tick.", at=SESSION_START)
        )
        assert len(telegram.sent) == 1
        assert whatsapp.sent == []


class TestRendering:
    def test_the_plain_renderer_emits_no_markup(self):
        """CallMeBot shows tags literally, so any markup here is a visible bug."""
        text = render(
            event(
                AlertKind.BREAK_CONFIRMED,
                role_before=LevelRole.RESISTANCE,
                role_after=LevelRole.SUPPORT,
            ),
            rich=False,
        )
        for markup in ("<b>", "</b>", "<code>", "<i>", "*", "_", "`"):
            assert markup not in text

    def test_the_rich_renderer_uses_html(self):
        text = render(event(AlertKind.BREAK_CONFIRMED), rich=True)
        assert "<b>" in text
        assert "<code>" in text

    @pytest.mark.parametrize("rich", [True, False])
    def test_a_role_flip_is_stated_in_both_renderers(self, rich):
        """'R1 broken' and 'R1 is now support' are the same fact, and only the
        second tells the reader what to do with it."""
        text = render(
            event(
                AlertKind.BREAK_CONFIRMED,
                role_before=LevelRole.RESISTANCE,
                role_after=LevelRole.SUPPORT,
            ),
            rich=rich,
        )
        assert "now acting as support" in text

    @pytest.mark.parametrize("rich", [True, False])
    def test_no_flip_is_claimed_when_the_role_did_not_change(self, rich):
        text = render(event(AlertKind.TOUCHED), rich=rich)
        assert "now acting as" not in text

    def test_both_renderers_carry_the_level_and_the_price(self):
        for rich in (True, False):
            text = render(event(AlertKind.TOUCHED), rich=rich)
            assert "24,700" in text
            assert "24,715" in text
            assert "R1" in text

    def test_direction_is_shown(self):
        up = render(event(AlertKind.TOUCHED), rich=False)
        assert "▲" in up  # price 24715 is above the 24700 level
