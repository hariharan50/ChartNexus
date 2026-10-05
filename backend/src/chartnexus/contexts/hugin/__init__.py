"""HUGIN — the desk's autonomous market memory.

HELLA reads the market, STRYX acts on it, HUGIN *remembers and learns from it*.

A proactive, per-tenant agent: from market open it wakes every hour, reads the
market through the same read-only tools HELLA/STRYX use, records a structured
observation with an explicit next-hour expectation, judges its previous hour's
read against what actually happened, distills lessons, and writes it all to a
durable per-tenant memory a read-only UI polls.

Like STRYX, this is its own bounded context: it imports no other context, and
every cross-context read is a sanctioned bridge in ``infrastructure/hugin``.
"""

from __future__ import annotations
