"""What a connection can ask to be sent, and how an event is matched to it.

A topic is the unit a browser subscribes to. The grammar is deliberately tiny —
``snapshots:NIFTY``, or ``snapshots:*`` for every symbol — because a topic string
is a public contract: it appears in client code, in logs, and in the websocket
schema under ``contracts/websocket/v1/``. Anything richer (strike ranges, expiry
filters) belongs in the REST read the client makes *after* this prompt, not in a
subscription grammar every client has to agree on.

Pure domain: no framework, no Redis, no FastAPI. Matching is a string compare,
which is what lets the delivery process route an event to several hundred
connections without touching a database.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from chartnexus.shared_kernel.domain.errors import ValidationError

#: The only stream there is today. Named rather than inlined so a second kind
#: (quotes, signals) is a one-line addition with the parser already enforcing it.
SNAPSHOTS: Final = "snapshots"

KINDS: Final[frozenset[str]] = frozenset({SNAPSHOTS})

#: Selector meaning "every symbol on this kind".
WILDCARD: Final = "*"

_SEPARATOR: Final = ":"

# Catalog symbols are upper-case alphanumerics (NIFTY, BANKNIFTY, MIDCPNIFTY,
# NIFTYNXT50). Validated here so a malformed subscription is refused at the edge
# with a clear code, rather than silently matching nothing forever — a client bug
# that is otherwise invisible from both sides.
_MAX_SYMBOL_LENGTH: Final = 32


@dataclass(frozen=True, slots=True, order=True)
class Topic:
    """A parsed, valid subscription target."""

    kind: str
    selector: str

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValidationError(
                f"'{self.kind}' is not a stream this server publishes.",
                kind=self.kind,
            )
        if self.selector != WILDCARD and not _is_symbol(self.selector):
            raise ValidationError(
                f"'{self.selector}' is not a valid symbol.",
                selector=self.selector,
            )

    @classmethod
    def parse(cls, raw: str) -> Topic:
        """Build a topic from its wire form, or raise :class:`ValidationError`.

        Case is preserved rather than normalised. A client that sends
        ``snapshots:nifty`` has a bug worth surfacing: the catalog is upper case,
        so quietly upper-casing it here would make the same client work against
        this server and fail against the REST surface it pairs with.
        """
        kind, separator, selector = raw.partition(_SEPARATOR)
        if not separator:
            raise ValidationError(
                "A topic looks like 'snapshots:NIFTY' or 'snapshots:*'.",
                topic=raw,
            )
        return cls(kind=kind, selector=selector)

    @property
    def is_wildcard(self) -> bool:
        return self.selector == WILDCARD

    def matches(self, kind: str, symbol: str) -> bool:
        """Does an event of ``kind`` about ``symbol`` belong on this topic?"""
        if kind != self.kind:
            return False
        return self.is_wildcard or self.selector == symbol

    def __str__(self) -> str:
        return f"{self.kind}{_SEPARATOR}{self.selector}"


def snapshots_for(symbol: str) -> Topic:
    """The concrete topic an event about ``symbol`` is delivered as.

    Wildcard subscribers are told the concrete topic too, so a client never has
    to reverse the match to learn which symbol moved.
    """
    return Topic(kind=SNAPSHOTS, selector=symbol)


def _is_symbol(value: str) -> bool:
    return (
        bool(value)
        and len(value) <= _MAX_SYMBOL_LENGTH
        and value.isascii()
        and value.isalnum()
        and value.upper() == value
    )
