"""Forward-return labels: direction, dead-band, and the end-of-series guard."""

from __future__ import annotations

import pytest

from marketcompass.contexts.signals.domain import labeling

pytestmark = pytest.mark.unit


def test_forward_return_is_the_fractional_move() -> None:
    closes = (100.0, 101.0, 103.0)
    assert labeling.forward_return(closes, 0, 2) == pytest.approx(0.03)


def test_forward_return_off_the_end_is_none() -> None:
    assert labeling.forward_return((100.0, 101.0), 1, 1) is None
    assert labeling.forward_return((100.0,), 0, 0) is None


def test_label_up_and_down() -> None:
    up = (100.0, 105.0)
    down = (100.0, 95.0)
    assert labeling.label_at(up, 0, 1) == 1
    assert labeling.label_at(down, 0, 1) == 0


def test_flat_move_inside_deadband_is_unlabelled() -> None:
    flat = (100.0, 100.02)  # +2 bps, inside the default 5 bps band
    assert labeling.label_at(flat, 0, 1) is None


def test_deadband_is_configurable() -> None:
    move = (100.0, 100.6)  # +60 bps
    assert labeling.label_at(move, 0, 1, deadband=0.005) == 1
    assert labeling.label_at(move, 0, 1, deadband=0.01) is None
