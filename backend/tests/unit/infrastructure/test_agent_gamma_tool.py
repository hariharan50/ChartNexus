"""The agents' gamma-exposure tool reads the latest GEX frame.

The GEX payload is a time series: flip, walls and net total live on each frame.
The tool used to read ``gamma_flip`` from the top level, which never exists, so
Hella, STRYX, MME100 and HUGIN all saw "gamma flip n/a" on every instrument
every day while the Gamma Exposure page showed the real level.
"""

from __future__ import annotations

from chartnexus.infrastructure.agent.langgraph.tools import _fmt_gamma


def _payload(**frame: object) -> dict[str, object]:
    base = {"t": "2026-11-19T10:00:00+00:00", "spot": 25514.3}
    return {"expiry_date": "2026-11-23", "frames": [{"t": "earlier"}, {**base, **frame}]}


def test_reads_the_latest_frame() -> None:
    text = _fmt_gamma(
        "NIFTY",
        _payload(gamma_flip=25539.86, net_total=-3711.05, call_wall=25500.0, put_wall=25300.0),
    )
    assert "gamma flip 25,540" in text
    assert "call wall 25,500" in text and "put wall 25,300" in text
    assert "short gamma" in text
    assert "expiry 2026-11-23" in text
    assert "n/a" not in text


def test_long_gamma_and_missing_levels() -> None:
    text = _fmt_gamma("BANKNIFTY", _payload(gamma_flip=None, net_total=1798.7))
    assert "long gamma" in text
    assert "gamma flip n/a" in text
    assert "None" not in text


def test_an_expired_chain_says_so() -> None:
    text = _fmt_gamma("SENSEX", _payload(net_total=0.0))
    assert "no gamma left" in text


def test_no_captures_yet() -> None:
    assert "unavailable" in _fmt_gamma("NIFTY", {"frames": []})
    assert "unavailable" in _fmt_gamma("NIFTY", {})
