"""Turn a request into the labels it is counted under.

Three rules matter more than the rest:

* **No query string, ever.** CallMeBot puts its API key in the query and
  Telegram puts the bot token in the path; neither may reach Redis. The query
  is never read, and Telegram's ``/bot<token>/`` segment is rewritten.
* **Paths become templates.** ``/instruments/historical/256265/minute`` and
  ``.../738561/day`` are one endpoint; counting them apart would turn one row
  into thousands.
* **Whose connection, not whose token.** The public app id is read from the
  broker's ``Authorization`` header and kept only as a short one-way hash, so a
  user's own view can be filtered to it. The token half is never looked at.
"""

from __future__ import annotations

import hashlib
import re

#: Host suffix -> provider label. First match wins.
_PROVIDERS: tuple[tuple[str, str], ...] = (
    ("kite.trade", "kite"),
    ("zerodha.com", "kite"),
    ("fyers.in", "fyers"),
    ("nseindia.com", "nse"),
    ("niftyindices.com", "nse"),
    ("nseix.com", "nseix"),
    ("yahoo.com", "yahoo"),
    ("telegram.org", "telegram"),
    ("callmebot.com", "whatsapp"),
    ("googleapis.com", "google"),
    ("google.com", "google"),
)

#: Brokers whose Authorization header carries the app id.
BROKERS = frozenset({"kite", "fyers"})

NO_APP = "-"
_MAX_SEGMENTS = 6
_MAX_ENDPOINT_LENGTH = 120
_OPAQUE_SEGMENT_LENGTH = 40

_TELEGRAM_BOT = re.compile(r"^bot[^/]+$", re.IGNORECASE)
_NUMERIC = re.compile(r"^[0-9][0-9.:_-]*$")
_HEXISH = re.compile(r"^[0-9a-f]{16,}$", re.IGNORECASE)
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)
_INTERVALS = frozenset(
    {
        "minute",
        "day",
        "week",
        "3minute",
        "5minute",
        "10minute",
        "15minute",
        "30minute",
        "60minute",
    }
)


def provider_for(host: str) -> str:
    host = host.lower().rstrip(".")
    for suffix, provider in _PROVIDERS:
        if host == suffix or host.endswith("." + suffix):
            return provider
    return "other"


def endpoint_template(path: str) -> str:
    """``/instruments/historical/256265/minute`` -> ``/instruments/historical/{id}/{interval}``."""
    parts: list[str] = []
    for segment in path.split("/"):
        if not segment:
            continue
        if len(parts) >= _MAX_SEGMENTS:
            parts.append("...")
            break
        if _TELEGRAM_BOT.match(segment):
            parts.append("bot{token}")
        elif _NUMERIC.match(segment) or _UUID.match(segment) or _HEXISH.match(segment):
            parts.append("{id}")
        elif segment.lower() in _INTERVALS:
            parts.append("{interval}")
        elif len(segment) > _OPAQUE_SEGMENT_LENGTH:
            parts.append("{value}")
        else:
            parts.append(segment.replace("|", "/"))
    return ("/" + "/".join(parts))[:_MAX_ENDPOINT_LENGTH]


def app_fingerprint(app_id: str) -> str:
    """A short, one-way label for a broker app id."""
    digest = hashlib.sha256(f"chartnexus-apimon:{app_id.strip()}".encode()).hexdigest()
    return digest[:12]


def app_from_authorization(provider: str, header: str | None) -> str:
    """The fingerprint of the app id in a broker ``Authorization`` header.

    Kite sends ``token <api_key>:<access_token>``, FYERS ``<app_id>:<access_token>``.
    Only the part before the first ``:`` is read.
    """
    if provider not in BROKERS or not header:
        return NO_APP
    value = header.strip()
    if value.lower().startswith("token "):
        value = value[len("token ") :]
    app_id, separator, _ = value.partition(":")
    if not separator or not app_id.strip():
        return NO_APP
    return app_fingerprint(app_id)
